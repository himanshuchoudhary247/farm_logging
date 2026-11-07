# 03: IAM instance role for Bedrock/Transcribe/Polly

**What to build:** The pilot box currently authenticates to AWS using a
personal IAM user's static access keys, sitting in plain text in
`runtime.env`. If the box is ever compromised, whoever gets in has that
human's AWS credentials, not just this app's. Replace it with an IAM role
attached to the instance (the repo's existing `aws/iam-bedrock-invoke.json`
policy already has the right permissions) so credentials are scoped to
exactly what this app needs and rotate automatically.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] An IAM role + instance profile exists, scoped to Bedrock invoke, Transcribe, Polly (per `aws/iam-bedrock-invoke.json`)
- [ ] The role is attached to the running instance
- [ ] `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` are removed from `runtime.env`
- [ ] A real chat turn (Bedrock call) and a voice turn (Transcribe/Polly call) both still succeed after the keys are removed
