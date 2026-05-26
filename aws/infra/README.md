AWS Infrastructure Setup (Initial Scaffold)

This sets up the foundation for:
- Bedrock LLM access
- Transcribe (speech-to-text)
- IAM roles and permissions

Prerequisites:
- AWS CLI configured
- Region supporting Bedrock (e.g. us-east-1)

Steps:
1. Create IAM policy:
   aws iam create-policy --policy-name farmer-chat-bedrock \
     --policy-document file://iam-bedrock-invoke.json

2. Attach policy to your user/role:
   aws iam attach-user-policy \
     --user-name <your-user> \
     --policy-arn arn:aws:iam::<account-id>:policy/farmer-chat-bedrock

3. Enable Bedrock model access in console

4. Set env vars:
   export AWS_REGION=us-east-1

Next steps:
- Add programmatic Bedrock client in llm adapters
- Add Transcribe integration
