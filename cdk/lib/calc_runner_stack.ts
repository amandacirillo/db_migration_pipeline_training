import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as logs from 'aws-cdk-lib/aws-logs';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';

/**
 * A training-sized copy of report-transformation-service's `DbFuncStack`: an SQS queue (backed
 * by a dead-letter queue) triggers a Lambda that runs a config-driven set of DB calculations.
 *
 * The two ideas worth a dedicated stack for:
 *   1. A DLQ with `maxReceiveCount` bounds how many times a poison-pill message gets retried
 *      before it's set aside for a human to look at, instead of endlessly reprocessing (and
 *      re-failing) the same broken message forever.
 *   2. `reservedConcurrentExecutions` caps how many of these Lambdas can run at once - without
 *      it, a burst of thousands of queued orders could each spin up their own concurrent
 *      execution and overwhelm the downstream database with connections.
 */
export interface CalcRunnerStackProps extends cdk.StackProps {
  maxReceiveCount?: number;
  reservedConcurrentExecutions?: number;
}

export class CalcRunnerStack extends cdk.Stack {
  public readonly queue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;
  public readonly calcRunnerFunction: lambda.Function;

  constructor(scope: Construct, id: string, props: CalcRunnerStackProps = {}) {
    super(scope, id, props);

    const maxReceiveCount = props.maxReceiveCount ?? 3;
    const reservedConcurrentExecutions = props.reservedConcurrentExecutions ?? 10;

    this.deadLetterQueue = new sqs.Queue(this, 'CalcRunnerDlq', {
      queueName: 'calc-runner-dlq',
      encryption: sqs.QueueEncryption.SQS_MANAGED,
    });

    this.queue = new sqs.Queue(this, 'CalcRunnerQueue', {
      queueName: 'calc-runner-queue',
      visibilityTimeout: cdk.Duration.minutes(5),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      deadLetterQueue: {
        queue: this.deadLetterQueue,
        maxReceiveCount,
      },
    });

    this.calcRunnerFunction = new lambda.Function(this, 'CalcRunnerFunction', {
      functionName: 'calc-runner',
      description: 'Runs the config-driven set of order-total calculations for one order.',
      runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      reservedConcurrentExecutions,
      // See apps/calc_runner/handler.py for the real handler code - a training-sized copy of
      // this repo synths cleanly with an inline stub, no build step required.
      code: lambda.Code.fromInline(
        'def handler(event, context):\n    raise NotImplementedError("placeholder - see apps/calc_runner/handler.py")\n',
      ),
      handler: 'index.handler',
      logGroup: new logs.LogGroup(this, 'CalcRunnerLogGroup', {
        logGroupName: '/aws/lambda/calc-runner',
        retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    this.calcRunnerFunction.addEventSource(
      new SqsEventSource(this.queue, {
        batchSize: 1,
      }),
    );

    new cdk.CfnOutput(this, 'QueueUrl', { value: this.queue.queueUrl });
    new cdk.CfnOutput(this, 'DeadLetterQueueUrl', { value: this.deadLetterQueue.queueUrl });
  }
}
