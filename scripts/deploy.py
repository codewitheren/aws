"""Run from the repository root with Python 3.11 and boto3 installed."""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import boto3

ROOT = Path(__file__).resolve().parents[1]
REGION = "us-east-1"
WEB = "tedarik-chat-web"
AGENT = "tedarik-chat-agent"
MODEL = os.environ.get("MODEL_ID", "us.anthropic.claude-opus-5")


def command(name, local):
    return shutil.which(name) or str(ROOT / local)


def aws(*args):
    subprocess.run([command("aws", ".build/cli/bin/aws"), "--region", REGION, *args], check=True, cwd=ROOT)


def client(name):
    return boto3.client(name, region_name=REGION)


def resource(stack, name):
    detail = client("cloudformation").describe_stack_resource(StackName=stack, LogicalResourceId=name)
    return detail["StackResourceDetail"]["PhysicalResourceId"]


def outputs(stack):
    result = client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0]
    return {row["OutputKey"]: row["OutputValue"] for row in result["Outputs"]}


def package():
    build = ROOT / ".build"
    build.mkdir(exist_ok=True)
    path = build / "agent.zip"
    with tempfile.TemporaryDirectory(dir=build) as stage:
        subprocess.run([command("uv", ".tools/bin/uv"), "--cache-dir", str(build/"cache"), "pip", "install",
                        "--python-version", "3.11", "--python-platform", "aarch64-manylinux_2_28",
                        "--only-binary", ":all:", "--target", stage, "-r", str(ROOT/"agent/requirements.txt")], check=True)
        for source in (ROOT/"agent").glob("*.py"):
            shutil.copy2(source, stage)
        shutil.copytree(ROOT/"agent/transfer", Path(stage)/"transfer",
                        ignore=shutil.ignore_patterns("__pycache__", "tests", "_yedek", "*.pyc"))
        history = ROOT / "data/data/izmir_gecmis"
        if history.is_dir():
            for item in history.glob("*/*/İzmir.parquet"):
                target = Path(stage) / "transfer/izmir_gecmis" / item.relative_to(history)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
            for file in sorted(Path(stage).rglob("*")):
                relative = file.relative_to(stage)
                if file.is_file() and not {"bin", "__pycache__"}.intersection(relative.parts) and file.suffix != ".pyc":
                    info = zipfile.ZipInfo(relative.as_posix())
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=5)
    return path


def deploy_runtime():
    bucket = resource(WEB, "Assets")
    artifact = package()
    key = f"runtime/{hashlib.sha256(artifact.read_bytes()).hexdigest()}.zip"
    client("s3").upload_file(str(artifact), bucket, key)
    aws("cloudformation", "deploy", "--stack-name", AGENT, "--template-file", "infra/runtime.yaml",
        "--capabilities", "CAPABILITY_IAM", "--no-fail-on-empty-changeset", "--parameter-overrides",
        f"Bucket={bucket}", f"CodeKey={key}", f"PoolId={resource(WEB, 'Pool')}",
        f"ClientId={resource(WEB, 'Client')}", f"ProfileId={MODEL}", f"FoundationModel={MODEL.removeprefix('us.')}")


def publish():
    web = outputs(WEB)
    arn = outputs(AGENT)["Arn"]
    s3 = client("s3")
    config = {"region": REGION, "clientId": web["ClientId"], "runtimeArn": arn, "model": MODEL}
    s3.put_object(Bucket=web["Bucket"], Key="web/config.json", Body=json.dumps(config).encode(),
                  ContentType="application/json", CacheControl="no-store")
    fe = ROOT / "fe"
    npm = command("npm", ".tools/bin/npm")
    if not (fe / "node_modules").exists():
        subprocess.run([npm, "ci"], check=True, cwd=fe)
    subprocess.run([npm, "run", "build"], check=True, cwd=fe, env={**os.environ, "VITE_AGENT_MODE": "agentcore"})
    dist = fe / "dist"
    # Hashed assets first and cached for good; index.html last so it never points at missing files.
    for file in sorted(dist.rglob("*"), key=lambda f: f.name == "index.html"):
        if file.is_file():
            hashed = file.parent.name == "assets"
            s3.upload_file(str(file), web["Bucket"], f"web/{file.relative_to(dist).as_posix()}",
                           ExtraArgs={"ContentType": mimetypes.guess_type(file.name)[0] or "text/plain",
                                      "CacheControl": "public, max-age=31536000, immutable" if hashed else "no-store"})
    print("https://" + web["Domain"], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", nargs="?", choices=["all", "runtime", "publish"], default="all")
    phase = parser.parse_args().phase
    if phase == "all":
        client("bedrock-runtime").converse(modelId=MODEL, messages=[{"role":"user","content":[{"text":"Reply OK."}]}],
                                           inferenceConfig={"maxTokens":256})
        aws("cloudformation", "deploy", "--stack-name", WEB, "--template-file", "infra/foundation.yaml",
            "--no-fail-on-empty-changeset")
    if phase in ("all", "runtime"):
        deploy_runtime()
    if phase in ("all", "publish"):
        publish()


if __name__ == "__main__":
    main()
