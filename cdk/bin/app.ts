import * as cdk from 'aws-cdk-lib';
import { CalcRunnerStack } from '../lib/calc_runner_stack';

const app = new cdk.App();

new CalcRunnerStack(app, 'CalcRunnerStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
  },
});
