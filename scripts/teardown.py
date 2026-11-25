"""Remove exactly this application's stacks, code, website and runtime log group."""
import argparse
from botocore.exceptions import ClientError
from deploy import AGENT, WEB, client, outputs

def existing(stack):
    try:
        return outputs(stack)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ValidationError" and "does not exist" in str(exc):
            return {}
        raise

def remove(cf, stack):
    cf.delete_stack(StackName=stack)
    cf.get_waiter("stack_delete_complete").wait(StackName=stack)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-account", required=True)
    args = parser.parse_args()
    if client("sts").get_caller_identity()["Account"] != args.confirm_account:
        parser.error("Hesap numarası uyuşmuyor.")
    cf = client("cloudformation")
    agent = existing(AGENT)
    if agent:
        group = "/aws/bedrock-agentcore/runtimes/" + agent["RuntimeId"] + "-DEFAULT"
        remove(cf, AGENT)
        logs = client("logs")
        try:
            logs.delete_log_group(logGroupName=group)
        except logs.exceptions.ResourceNotFoundException:
            pass
    web = existing(WEB)
    if web:
        s3 = client("s3")
        for prefix in ("web/", "runtime/"):
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=web["Bucket"], Prefix=prefix):
                keys = [{"Key": row["Key"]} for row in page.get("Contents", [])]
                if keys:
                    reply = s3.delete_objects(Bucket=web["Bucket"], Delete={"Objects":keys})
                    if reply.get("Errors"):
                        raise RuntimeError(reply["Errors"])
        remove(cf, WEB)
    print("Proje kaynakları kaldırıldı.")

if __name__ == "__main__":
    main()
