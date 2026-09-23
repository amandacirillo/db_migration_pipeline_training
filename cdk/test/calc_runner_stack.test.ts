import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { CalcRunnerStack } from '../lib/calc_runner_stack';

describe('CalcRunnerStack', () => {
  function synth(props: ConstructorParameters<typeof CalcRunnerStack>[2] = {}) {
    const app = new cdk.App();
    const stack = new CalcRunnerStack(app, 'TestStack', {
      env: { account: '111111111111', region: 'us-east-1' },
      ...props,
    });
    return Template.fromStack(stack);
  }

  it('wires the queue to a dead-letter queue with the default maxReceiveCount', () => {
    const template = synth();
    template.hasResourceProperties('AWS::SQS::Queue', {
      QueueName: 'calc-runner-queue',
      RedrivePolicy: Match.objectLike({ maxReceiveCount: 3 }),
    });
    template.hasResourceProperties('AWS::SQS::Queue', { QueueName: 'calc-runner-dlq' });
  });

  it('honors a custom maxReceiveCount', () => {
    const template = synth({ maxReceiveCount: 5 });
    template.hasResourceProperties('AWS::SQS::Queue', {
      QueueName: 'calc-runner-queue',
      RedrivePolicy: Match.objectLike({ maxReceiveCount: 5 }),
    });
  });

  it('caps the Lambda\'s reserved concurrency', () => {
    const template = synth();
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'calc-runner',
      ReservedConcurrentExecutions: 10,
    });
  });

  it('triggers the Lambda from the queue with a batch size of 1', () => {
    const template = synth();
    template.hasResourceProperties('AWS::Lambda::EventSourceMapping', {
      BatchSize: 1,
    });
  });
});
