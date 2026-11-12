#!/usr/bin/env python3
"""
The pre-build (prebuild.py) on a rented 64-core AWS machine instead of the Mac Mini: a whole cache in about 2 hours
of building instead of 19-28 on the Mini (the cache rebuild speed report, https://claude.ai/artifact/8jAZEuhY56MEkP8waUNfm4;
Sam picked it 2026-10-27). The machine runs this repo's own pre-build, at one commit, on the Mini's own inputs (the
lean archive and the geometry cache; no SPICE kernels, since every frame's geometry is in that cache), so it makes
the Mini's pictures: the same files, and the same pixels but for a few a level apart where two machines' math
libraries round a last digit differently (rebuild_bench.py). Build each cache version on one machine.

One S3 bucket, cassini-rebuild-<account>-<region>, holds it all:
  inputs/cassini_lut8.zip, inputs/geometry.sqlite   copied up from the Mini once (upload-inputs)
  code/<commit>.tar.gz                               the commit a machine builds with (git archive)
  runs/<run>/run.json, only.txt                      a run's choices (launch)
  runs/<run>/status.json, log.txt                    the machine's heartbeat and log (work)
  runs/<run>/out/served-NNNNN.tar, work-NNNNN.tar    what it made, in tar shards of about 4 GB, as each phase ends:
                                                     what the frame server serves, and apart from it the passes'
                                                     working files (tile pictures, filter levels), which only
                                                     drawing a pass again reads (on the Mini they live on the LaCie)
  runs/<run>/manifest.json                           every shard with its files and hash, each phase's time

Where the AWS key is (the cloud environment's Network secrets; its policy: cassini-rebuild-policy.json):
  python web/frames/cloud_rebuild.py check              who, spot prices, the 64-core quota, the bucket and inputs
  python web/frames/cloud_rebuild.py setup              makes the bucket, asks AWS for the quota
  python web/frames/cloud_rebuild.py creds --hours 12   short-lived keys to the bucket alone, for the Mini
  python web/frames/cloud_rebuild.py launch [--phases movies,strips] [--only FILE] [--commit origin/main]
  python web/frames/cloud_rebuild.py status [--run RUN]
  python web/frames/cloud_rebuild.py stop --run RUN
On the Mini, with creds' keys in the environment and boto3 installed:
  python web/frames/cloud_rebuild.py upload-inputs --archive /Volumes/LaCie/cassini_lut8.zip --geometry ... --tmp DIR
  python web/frames/cloud_rebuild.py fetch --run RUN --to <cache> [--work-to <folder>] [--compare <live cache>]
On the machine (its start-up script, BOOT, runs it):
  python web/frames/cloud_rebuild.py work --run RUN
"""
import argparse
import datetime
import hashlib
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TAG = "cassini-rebuild"                              # the project tag the key may start and stop machines with
REGIONS = ("us-east-2", "us-east-1", "us-west-2")    # the regions the key's policy allows
TYPES = ("m8a.16xlarge", "c8a.16xlarge", "m7a.16xlarge", "c7a.16xlarge")   # 64 cores each (AMD: a vCPU is a core)
QUOTA_SPOT, QUOTA_ON_DEMAND = "L-34B43A08", "L-1216C47A"   # vCPUs of standard machines at once: spot, on demand
INPUTS = {"archive": "inputs/cassini_lut8.zip", "geometry": "inputs/geometry.sqlite"}
SHARD = 4 << 30      # bytes of files in one tar shard
BEAT = 30            # s between a machine's heartbeats
DISK_GB = 800        # the machine's disk: archive 73 GB, served cache ~161, working files ~277, shards in flight
EBS_PER_HOUR = 0.22  # $ an hour for that disk (gp3 800 GB at 16,000 IOPS and 1,000 MB/s)
EGRESS = 0.09        # $ a GB out of AWS (to the Mini)
WORK = os.environ.get("CASSINI_CLOUD_WORK", "/work")   # where the machine builds (another folder for a test)


# ---------- AWS ----------

def client(service, region=None):
    import boto3
    from botocore.config import Config
    return boto3.client(service, region_name=region or os.environ.get("AWS_DEFAULT_REGION") or REGIONS[0],
                        config=Config(retries={"max_attempts": 10, "mode": "adaptive"}))


def transfer(chunk_mb=128, threads=16):
    from boto3.s3.transfer import TransferConfig
    return TransferConfig(multipart_threshold=64 << 20, multipart_chunksize=chunk_mb << 20, max_concurrency=threads)


def bucket():
    """(name, region) of the build bucket: CASSINI_BUCKET where creds' keys are (they name it), else the one this
    account has in one of REGIONS, else (None, None)."""
    from botocore.exceptions import ClientError
    if os.environ.get("CASSINI_BUCKET"):
        name = os.environ["CASSINI_BUCKET"]
        return name, name.split("-", 3)[3]
    account = client("sts").get_caller_identity()["Account"]
    for region in REGIONS:
        name = f"{TAG}-{account}-{region}"
        try:
            client("s3", region).head_bucket(Bucket=name)
            return name, region
        except ClientError:
            continue
    return None, None


def head(s3, name, key):
    from botocore.exceptions import ClientError
    try:
        return s3.head_object(Bucket=name, Key=key)
    except ClientError:
        return None


def get_json(s3, name, key):
    from botocore.exceptions import ClientError
    try:
        return json.loads(s3.get_object(Bucket=name, Key=key)["Body"].read())
    except ClientError:
        return None


def put_json(s3, name, key, data):
    s3.put_object(Bucket=name, Key=key, Body=json.dumps(data, indent=1).encode(), ContentType="application/json")


def spot_prices(regions=REGIONS, types=TYPES):
    """{(region, zone, type): the latest spot price, $ an hour} over the last three hours."""
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
    latest = {}
    for region in regions:
        pages = client("ec2", region).get_paginator("describe_spot_price_history").paginate(
            InstanceTypes=list(types), ProductDescriptions=["Linux/UNIX"], StartTime=since)
        for page in pages:
            for p in page["SpotPriceHistory"]:
                k = (region, p["AvailabilityZone"], p["InstanceType"])
                if k not in latest or p["Timestamp"] > latest[k][1]:
                    latest[k] = (float(p["SpotPrice"]), p["Timestamp"])
    return {k: v[0] for k, v in latest.items()}


def quota(region, code):
    """vCPUs of standard machines the account may run at once in region (spot or on demand, by quota code)."""
    from botocore.exceptions import ClientError
    sq = client("service-quotas", region)
    try:
        return sq.get_service_quota(ServiceCode="ec2", QuotaCode=code)["Quota"]["Value"]
    except ClientError:
        return sq.get_aws_default_service_quota(ServiceCode="ec2", QuotaCode=code)["Quota"]["Value"]


def asked(region, code):
    """The quota increase already asked for and not yet answered (its wanted value), or None."""
    hist = client("service-quotas", region).list_requested_service_quota_change_history_by_quota(
        ServiceCode="ec2", QuotaCode=code).get("RequestedQuotas", [])
    open_ = [r for r in hist if r["Status"] in ("PENDING", "CASE_OPENED")]
    return max((r["DesiredValue"] for r in open_), default=None)


def bucket_policy(name, write):
    """A session policy for short-lived keys (GetFederationToken): read the bucket, write under write only."""
    return {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation", "s3:ListBucketMultipartUploads"],
         "Resource": f"arn:aws:s3:::{name}"},
        {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": f"arn:aws:s3:::{name}/*"},
        {"Effect": "Allow", "Action": ["s3:PutObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"],
         "Resource": f"arn:aws:s3:::{name}/{write}"}]}


def keys(name, who, write, hours):
    """Short-lived keys (at most 36 hours) that can only read the bucket and write under write."""
    return client("sts").get_federation_token(Name=who[:32], DurationSeconds=int(min(36, max(0.25, hours)) * 3600),
                                              Policy=json.dumps(bucket_policy(name, write)))["Credentials"]


# ---------- the driver (where the AWS key is) ----------

def check(args):
    from botocore.exceptions import ClientError, NoCredentialsError
    try:
        me = client("sts").get_caller_identity()
    except (ClientError, NoCredentialsError) as e:
        code = e.response["Error"]["Code"] if isinstance(e, ClientError) else type(e).__name__
        sys.exit(f"AWS refused the key ({code}): the cassini-rebuild user's AWS_ACCESS_KEY_ID and "
                 "AWS_SECRET_ACCESS_KEY are not set here, or not valid")
    print(f"AWS account {me['Account']} as {me['Arn']}")
    name, region = bucket()
    print(f"bucket: {name or 'none yet (setup makes it)'}")
    prices = spot_prices()
    for t in TYPES:
        best = sorted((p, r, z) for (r, z, tt), p in prices.items() if tt == t)
        print(f"  {t}: " + (f"${best[0][0]:.2f}/h spot in {best[0][2]}, {len(best)} zones" if best else "no spot price"))
    for r in ([region] if region else REGIONS):
        for what, code in (("spot", QUOTA_SPOT), ("on demand", QUOTA_ON_DEMAND)):
            try:
                pending = asked(r, code)
                print(f"  {r} {what}: {quota(r, code):.0f} vCPUs at once" + (f" (asked for {pending:.0f})" if pending else ""))
            except Exception as e:   # noqa: BLE001
                print(f"  {r} {what}: the quota could not be read ({type(e).__name__})")
    if name:
        s3 = client("s3", region)
        for what, key in INPUTS.items():
            h = head(s3, name, key)
            print(f"  {what}: " + (f"{h['ContentLength'] / 1e9:.1f} GB, {h['LastModified']:%Y-%m-%d %H:%M}Z" if h else "not uploaded"))


def setup(args):
    """The bucket (in the region where the first of TYPES is cheapest, unless --region), closed to the public, with
    unfinished uploads cleared after 2 days and runs after --keep-days; then the quota asked for where it is short."""
    account = client("sts").get_caller_identity()["Account"]
    name, region = bucket()
    if not name:
        if args.region:
            region = args.region
        else:
            prices = spot_prices(types=TYPES[:1])
            region = min(prices.items(), key=lambda kv: kv[1])[0][0] if prices else REGIONS[0]
        name = f"{TAG}-{account}-{region}"
        s3 = client("s3", region)
        s3.create_bucket(Bucket=name, **({} if region == "us-east-1" else
                                         {"CreateBucketConfiguration": {"LocationConstraint": region}}))
        s3.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={
            k: True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")})
        s3.put_bucket_lifecycle_configuration(Bucket=name, LifecycleConfiguration={"Rules": [
            {"ID": "unfinished-uploads", "Status": "Enabled", "Filter": {"Prefix": ""},
             "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}},
            {"ID": "old-runs", "Status": "Enabled", "Filter": {"Prefix": "runs/"}, "Expiration": {"Days": args.keep_days}}]})
        print(f"made bucket {name}")
    else:
        print(f"bucket {name} is there")
    sq = client("service-quotas", region)
    for what, code in (("spot", QUOTA_SPOT), ("on demand", QUOTA_ON_DEMAND)):
        try:
            have, pending = quota(region, code), asked(region, code)
        except Exception as e:   # noqa: BLE001
            print(f"{what}: the quota could not be read ({type(e).__name__}: {e})")
            continue
        if have >= args.vcpus:
            print(f"{what}: {have:.0f} vCPUs, enough")
        elif pending and pending >= args.vcpus:
            print(f"{what}: {have:.0f} vCPUs, {pending:.0f} asked for already")
        else:
            sq.request_service_quota_increase(ServiceCode="ec2", QuotaCode=code, DesiredValue=float(args.vcpus))
            print(f"{what}: {have:.0f} vCPUs, asked AWS for {args.vcpus}")


def creds(args):
    """Keys for the Mini, as shell exports: read the bucket, write its inputs (upload-inputs), for --hours."""
    name, region = bucket()
    if not name:
        sys.exit("no bucket yet: run setup")
    c = keys(name, "cassini-mini", "inputs/*", args.hours)
    print(f"export AWS_ACCESS_KEY_ID={c['AccessKeyId']} AWS_SECRET_ACCESS_KEY={c['SecretAccessKey']} "
          f"AWS_SESSION_TOKEN={c['SessionToken']} AWS_DEFAULT_REGION={region} CASSINI_BUCKET={name}")
    print(f"# good until {c['Expiration']:%Y-%m-%d %H:%M}Z", file=sys.stderr)


BOOT = r"""#!/bin/bash
# cassini-rebuild @RUN@: the machine's start-up script (cloud_rebuild.py launch); the build itself is
# cloud_rebuild.py work. The machine is shut down, which ends it (terminate on shutdown), when work is done or fails,
# and after @MAX_MIN@ minutes whatever happens.
exec > >(tee -a /var/log/cassini-rebuild.log) 2>&1
set -u
shutdown -h +@MAX_MIN@
export AWS_ACCESS_KEY_ID='@KEY@' AWS_SECRET_ACCESS_KEY='@SECRET@' AWS_SESSION_TOKEN='@TOKEN@' AWS_DEFAULT_REGION=@REGION@
B=@BUCKET@ RUN=@RUN@
beat() { printf '{"run": "%s", "state": "%s", "updated": %s}' "$RUN" "$1" "$(date +%s)" | aws s3 cp - "s3://$B/runs/$RUN/status.json" --quiet; }
finish() { aws s3 cp /var/log/cassini-rebuild.log "s3://$B/runs/$RUN/log.txt" --quiet; shutdown -h now; }
trap finish EXIT
beat "installing"
dnf install -y -q python3.11 python3.11-pip python3.11-pip-wheel mesa-libGL glib2 sqlite tar \
  || { beat "failed: installing packages"; exit 1; }
mkdir -p /work/repo
aws s3 cp "s3://$B/code/@COMMIT@.tar.gz" - --quiet | tar -xz -C /work/repo || { beat "failed: getting the code"; exit 1; }
python3.11 -m venv /work/venv && /work/venv/bin/pip install -q -r /work/repo/requirements.txt boto3 \
  || { beat "failed: installing the Python packages"; exit 1; }
/work/venv/bin/python -c "import cv2, numpy, PIL, scipy, skimage, matplotlib, pandas, spiceypy, boto3" \
  || { beat "failed: importing the Python packages (see log.txt)"; exit 1; }
/work/venv/bin/python /work/repo/web/frames/cloud_rebuild.py work --run "$RUN" --bucket "$B" || beat "failed: work (see log.txt)"
"""


def phases_of_prebuild():
    """prebuild.PHASES, in its order, read from its source (importing it loads the whole pipeline)."""
    import ast
    with open(os.path.join(HERE, "prebuild.py")) as fh:
        for node in ast.parse(fh.read()).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "PHASES" for t in node.targets):
                return tuple(ast.literal_eval(node.value))
    raise RuntimeError("no PHASES in prebuild.py")


def running(region, run=None):
    """The project's machines that are starting or running (of one run)."""
    filters = [{"Name": "tag:project", "Values": [TAG]}, {"Name": "instance-state-name", "Values": ["pending", "running"]}]
    if run:
        filters.append({"Name": "tag:run", "Values": [run]})
    out = client("ec2", region).describe_instances(Filters=filters)
    return [i for r in out["Reservations"] for i in r["Instances"]]


def launch(args):
    """Rents the machine for a run: the commit's code and the run's choices into the bucket, then a spot machine
    (or --on-demand) of the first of --types with a free zone, cheapest zone first, whose start-up script (BOOT)
    builds it all and shuts the machine down."""
    from botocore.exceptions import ClientError
    name, region = bucket()
    if not name:
        sys.exit("no bucket yet: run setup")
    s3 = client("s3", region)
    missing = [what for what, key in INPUTS.items() if not head(s3, name, key)]
    if missing:
        sys.exit(f"inputs not uploaded yet: {', '.join(missing)} (upload-inputs, on the Mini)")
    if running(region) and not args.parallel:
        sys.exit("a build machine is already running (status; or --parallel)")
    phases = args.phases.split(",") if args.phases else list(phases_of_prebuild())
    unknown = set(phases) - set(phases_of_prebuild())
    if unknown:
        sys.exit(f"no such phase: {', '.join(sorted(unknown))}")
    commit = subprocess.run(["git", "-C", REPO, "rev-parse", args.commit], capture_output=True, text=True, check=True).stdout.strip()
    code = f"code/{commit}.tar.gz"
    if not head(s3, name, code):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "code.tar.gz")
            subprocess.run(["git", "-C", REPO, "archive", "--format=tar.gz", "-o", path, commit], check=True)
            s3.upload_file(path, name, code, Config=transfer())
    run = args.run or f"{datetime.datetime.now(datetime.timezone.utc):%Y%m%d-%H%M%S}-{commit[:7]}"
    if args.only:
        s3.upload_file(os.path.expanduser(args.only), name, f"runs/{run}/only.txt")
    types = args.types.split(",") if args.types else list(TYPES)
    cfg = {"run": run, "bucket": name, "region": region, "commit": commit, "phases": phases, "only": bool(args.only),
           "procs": args.procs, "work_files": not args.served_only, "spot": not args.on_demand,
           "max_hours": args.max_hours, "launched": time.time()}
    put_json(s3, name, f"runs/{run}/run.json", cfg)
    c = keys(name, f"cassini-{run}", f"runs/{run}/*", args.max_hours + 1)
    boot = BOOT
    for k, v in {"RUN": run, "BUCKET": name, "REGION": region, "COMMIT": commit, "MAX_MIN": str(int(args.max_hours * 60)),
                 "KEY": c["AccessKeyId"], "SECRET": c["SecretAccessKey"], "TOKEN": c["SessionToken"]}.items():
        boot = boot.replace(f"@{k}@", v)
    ec2 = client("ec2", region)
    if args.image:
        image = ec2.describe_images(ImageIds=[args.image])["Images"][0]
    else:   # the newest Amazon Linux 2023 (its Python 3.11 and the pinned packages' wheels: requirements.txt)
        image = max(ec2.describe_images(Owners=["amazon"], Filters=[
            {"Name": "name", "Values": ["al2023-ami-2023.*-kernel-*-x86_64"]}, {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]}])["Images"], key=lambda i: i["CreationDate"])
    zones = {s["AvailabilityZone"]: s["SubnetId"] for s in ec2.describe_subnets(
        Filters=[{"Name": "default-for-az", "Values": ["true"]}])["Subnets"]}
    if not zones:
        sys.exit(f"no default network (VPC) in {region}")
    prices = spot_prices([region], types)
    tries = sorted(((prices.get((region, z, t), 99.0) if cfg["spot"] else 0, types.index(t), t, z)
                    for t in types for z in zones), key=lambda x: (x[1], x[0]))
    tags = [{"Key": "project", "Value": TAG}, {"Key": "run", "Value": run}, {"Key": "Name", "Value": f"{TAG} {run}"}]
    for price, _, t, z in tries:
        if cfg["spot"] and price >= 99:
            continue   # not offered in that zone
        try:
            out = ec2.run_instances(
                ImageId=image["ImageId"], InstanceType=t, MinCount=1, MaxCount=1, SubnetId=zones[z], UserData=boot,
                InstanceInitiatedShutdownBehavior="terminate", MetadataOptions={"HttpTokens": "required"},
                BlockDeviceMappings=[{"DeviceName": image["RootDeviceName"], "Ebs": {
                    "VolumeSize": args.disk, "VolumeType": "gp3", "Iops": 16000, "Throughput": 1000, "DeleteOnTermination": True}}],
                TagSpecifications=[{"ResourceType": rt, "Tags": tags}
                                   for rt in ("instance", "volume") + (("spot-instances-request",) if cfg["spot"] else ())],
                **({"InstanceMarketOptions": {"MarketType": "spot", "SpotOptions": {
                    "SpotInstanceType": "one-time", "InstanceInterruptionBehavior": "terminate"}}} if cfg["spot"] else {}))
        except ClientError as e:
            code_ = e.response["Error"]["Code"]
            if code_ in ("InsufficientInstanceCapacity", "SpotMaxPriceTooLow", "Unsupported", "MaxSpotInstanceCountExceeded",
                         "InstanceLimitExceeded", "VcpuLimitExceeded"):
                print(f"{t} in {z}: {code_}, trying the next")
                continue
            raise
        inst = out["Instances"][0]
        cfg.update(instance=inst["InstanceId"], type=t, zone=z, price=price if cfg["spot"] else None, image=image["ImageId"])
        put_json(s3, name, f"runs/{run}/run.json", cfg)
        print(f"run {run}: {t} in {z}" + (f" at ${price:.2f}/h spot" if cfg["spot"] else " on demand") +
              f", {inst['InstanceId']}, phases {','.join(phases)}; it ends itself within {args.max_hours:g} h")
        print(f"  python web/frames/cloud_rebuild.py status --run {run}")
        return
    sys.exit("no machine to be had (capacity or quota): try later, --on-demand, or other --types")


def runs(s3, name):
    out = s3.list_objects_v2(Bucket=name, Prefix="runs/", Delimiter="/")
    return sorted(p["Prefix"].split("/")[1] for p in out.get("CommonPrefixes", []))


def status(args):
    name, region = bucket()
    s3 = client("s3", region)
    run = args.run or (runs(s3, name) or [None])[-1]
    if not run:
        sys.exit("no runs yet")
    cfg = get_json(s3, name, f"runs/{run}/run.json") or {}
    beat = get_json(s3, name, f"runs/{run}/status.json") or {}
    machines = running(region, run)
    end = time.time() if machines else (beat.get("updated") or time.time())
    hours = (end - cfg.get("launched", end)) / 3600
    print(f"run {run}: {cfg.get('type')} {cfg.get('zone')}, phases {','.join(cfg.get('phases', []))}, "
          f"{'running' if machines else 'machine gone'}, {hours:.2f} h" + (" since launch" if machines else " from launch to its last heartbeat"))
    if beat:
        age = time.time() - beat.get("updated", 0)
        pb = beat.get("prebuild") or {}
        line = f"  {beat.get('state')}" + (f" {beat['phase']}" if beat.get("phase") else "")
        if pb.get("total"):
            line += f": {pb.get('done', 0):,}/{pb['total']:,}" + (f", {pb['errors']} errors" if pb.get("errors") else "")
            if pb.get("eta_s"):
                line += f", ~{pb['eta_s'] / 60:.0f} min left in the phase"
        print(line + f" (heartbeat {age:.0f} s ago)")
        for p in beat.get("phases_done", []):
            print(f"  done {p['phase']}: {p['s'] / 60:.1f} min, {p.get('done', 0):,} items, {p.get('errors', 0)} errors, exit {p['exit']}")
        sh = beat.get("shipped") or {}
        if sh:
            print(f"  shipped {sh.get('shards', 0)} shards, {sh.get('bytes', 0) / 1e9:.1f} GB "
                  f"({sh.get('served_bytes', 0) / 1e9:.1f} served, {sh.get('work_bytes', 0) / 1e9:.1f} working files; "
                  f"{sh.get('pruned_bytes', 0) / 1e9:.1f} GB of filter levels left out as the sweeper prunes them)")
        if beat.get("geometry_misses"):
            print(f"  geometry: {beat['geometry_misses']:,} frames were not in the geometry cache, and with no kernels "
                  f"the machine could not centre them: their pictures may differ from the Mini's")
        for k in ("load", "disk_used_gb", "mem_used_gb"):
            if k in beat:
                print(f"  {k}: {beat[k]}")
    else:
        print("  no heartbeat yet")
    if cfg.get("price") is not None or cfg.get("type"):
        cost = hours * ((cfg.get("price") or 3.9) + EBS_PER_HOUR)
        print(f"  machine so far ~${cost:.2f}" + (" (on-demand rate guessed)" if cfg.get("price") is None else ""))
    if machines and (not beat or time.time() - beat.get("updated", 0) > 600):
        out = client("ec2", region).get_console_output(InstanceId=machines[0]["InstanceId"], Latest=True).get("Output", "")
        print("  console:\n" + "\n".join("    " + line for line in out.splitlines()[-15:]))


def stop(args):
    name, region = bucket()
    ids = [i["InstanceId"] for i in running(region, args.run)]
    if ids:
        client("ec2", region).terminate_instances(InstanceIds=ids)
    print(f"stopped {', '.join(ids)}" if ids else "nothing running for that run")


# ---------- on the machine ----------

def is_work(rel):
    """Whether a cache file is a pass's working file (a tile's picture, its filter levels): read only to draw the
    pass again, so the Mini keeps them on the LaCie, apart from what it serves."""
    parts = rel.split(os.sep)
    return "filters-level" in parts[:-1] or (any(p.startswith("tiles-") for p in parts[:-1]) and rel.endswith(".png"))


def geometry_new(path, after=0):
    """The geometry cache's last row, and the frames it got after row after: frames the build had to work out on the
    machine, where there are no kernels (the lean archive has none), so failures the Mini's build did not have.
    (last row, how many, the first 50)."""
    db = sqlite3.connect(path)
    try:
        last = db.execute("SELECT coalesce(max(rowid), 0) FROM target").fetchone()[0]
        n = db.execute("SELECT count(*) FROM target WHERE rowid > ?", (after,)).fetchone()[0]
        first = [r[0] for r in db.execute("SELECT frame FROM target WHERE rowid > ? ORDER BY rowid LIMIT 50", (after,))]
    finally:
        db.close()
    return last, n, first


class Shipper:
    """Ships what the machine made into the bucket while it builds on: at each phase's end, every file made before
    then and not shipped yet, as tar shards of about SHARD bytes (served and working files apart)."""

    def __init__(self, s3, name, run, cache, work_files):
        self.s3, self.name, self.run, self.cache, self.work_files = s3, name, run, cache, work_files
        self.sent, self.shards, self.n = set(), [], 0
        self.totals = {"shards": 0, "bytes": 0, "files": 0, "served_bytes": 0, "work_bytes": 0, "skipped_work_bytes": 0,
                       "pruned_bytes": 0}
        self.q = queue.Queue()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def ship(self, phase, before):
        self.q.put((phase, before))

    def finish(self):
        self.q.put(None)
        self.thread.join()

    def _loop(self):
        while True:
            job = self.q.get()
            if job is None:
                return
            try:
                self._ship(*job)
            except Exception as e:   # noqa: BLE001  (said in the heartbeat and the manifest; the build goes on)
                self.totals["error"] = f"{type(e).__name__}: {e}"[:300]

    def _ship(self, phase, before):
        # made before the phase's end: a file the next phase is writing (a tile picture is written in place) waits
        new = {"served": [], "work": []}
        for root, _, files in os.walk(self.cache):
            for f in files:
                path = os.path.join(root, f)
                rel = os.path.relpath(path, self.cache)
                if rel in self.sent or f.endswith(".part"):
                    continue
                st = os.stat(path)
                if st.st_mtime >= before:
                    continue
                new["work" if is_work(rel) else "served"].append((rel, st.st_size))
        for kind in ("served", "work"):
            files = sorted(new[kind])
            if kind == "work" and not self.work_files:
                self.totals["skipped_work_bytes"] += sum(s for _, s in files)
                self.sent.update(r for r, _ in files)
                continue
            if kind == "work":
                files = self._pruned(files)
            chunk, size = [], 0
            for rel, s in files + [(None, 0)]:
                if rel is None or (chunk and size + s > SHARD):
                    if chunk:
                        self._tar(kind, phase, chunk, size)
                    chunk, size = [], 0
                if rel is not None:
                    chunk.append(rel)
                    size += s

    def _pruned(self, files):
        """files without the filters-level pictures the Mini's sweeper prunes (filters_prune.doomed: of each filter
        it keeps the newest count and every 16th), which no served picture needs: they are never shipped."""
        from filters_prune import doomed
        out, gone = [], {}
        for rel, s in files:
            folder, f = os.path.split(rel)
            if "filters-level" in folder.split(os.sep):
                if folder not in gone:
                    gone[folder] = set(doomed(os.listdir(os.path.join(self.cache, folder))))
                if f in gone[folder]:
                    self.totals["pruned_bytes"] += s
                    self.sent.add(rel)
                    continue
            out.append((rel, s))
        return out

    def _tar(self, kind, phase, rels, size):
        self.n += 1
        base = f"{kind}-{self.n:05d}"
        os.makedirs(os.path.join(WORK, "shards"), exist_ok=True)
        tar, listing = os.path.join(WORK, "shards", base + ".tar"), os.path.join(WORK, "shards", base + ".txt")
        with open(listing, "w") as fh:
            fh.write("".join(r + "\n" for r in rels))
        subprocess.run(["tar", "-cf", tar, "-C", self.cache, "--verbatim-files-from", "-T", listing], check=True)
        h = hashlib.sha256()
        with open(tar, "rb") as fh:
            for block in iter(lambda: fh.read(8 << 20), b""):
                h.update(block)
        key = f"runs/{self.run}/out/{base}.tar"
        self.s3.upload_file(tar, self.name, key, Config=transfer(), ExtraArgs={"Metadata": {
            "sha256": h.hexdigest(), "files": str(len(rels)), "kind": kind, "phase": phase}})
        tar_bytes = os.path.getsize(tar)
        os.remove(tar)
        os.remove(listing)
        self.sent.update(rels)
        self.shards.append({"key": key, "kind": kind, "phase": phase, "files": len(rels), "bytes": tar_bytes,
                            "file_bytes": size, "sha256": h.hexdigest()})
        self.totals["shards"] += 1
        self.totals["bytes"] += tar_bytes
        self.totals["files"] += len(rels)
        self.totals[f"{kind}_bytes"] += tar_bytes


def work(args):
    """The build, on the machine: the inputs from the bucket, every phase of the run as prebuild.py --procs N
    --balanced (all the machine's cores, the longest passes first), what each phase made shipped back into the bucket
    as it ends, a heartbeat every BEAT seconds, then the manifest."""
    name, region = args.bucket or os.environ.get("CASSINI_BUCKET"), os.environ.get("AWS_DEFAULT_REGION")
    s3 = client("s3", region)
    cfg = get_json(s3, name, f"runs/{args.run}/run.json")
    run = cfg["run"]
    data, cache, stat = (os.path.join(WORK, d) for d in ("data", "cache", "status"))
    for d in (data, cache, stat):
        os.makedirs(d, exist_ok=True)
    state = {"run": run, "state": "getting the inputs", "phase": None, "phases_done": [], "started": time.time()}
    shipper = None

    def heartbeat():
        while True:
            try:
                s = dict(state, updated=time.time(), load=[round(x, 1) for x in os.getloadavg()],
                         disk_used_gb=round(shutil.disk_usage(WORK).used / 1e9, 1))
                with open("/proc/meminfo") as fh:
                    mem = {line.split(":")[0]: int(line.split()[1]) for line in fh}
                s["mem_used_gb"] = round((mem["MemTotal"] - mem["MemAvailable"]) / 1e6, 1)
                if state.get("phase"):
                    try:
                        with open(os.path.join(stat, "status.json")) as fh:
                            s["prebuild"] = json.load(fh)
                    except (OSError, ValueError):
                        pass
                if shipper:
                    s["shipped"] = dict(shipper.totals)
                put_json(s3, name, f"runs/{run}/status.json", s)
                if int(time.time()) % 120 < BEAT and os.path.exists("/var/log/cassini-rebuild.log"):
                    s3.upload_file("/var/log/cassini-rebuild.log", name, f"runs/{run}/log.txt")
            except Exception as e:   # noqa: BLE001  (a missed heartbeat is not worth the build)
                print(f"heartbeat: {e}", flush=True)
            time.sleep(BEAT)
    threading.Thread(target=heartbeat, daemon=True).start()

    t0 = time.time()
    archive, geometry = os.path.join(data, "cassini_lut8.zip"), os.path.join(data, "geometry.sqlite")
    for key, path in ((INPUTS["archive"], archive), (INPUTS["geometry"], geometry)):
        s3.download_file(name, key, path, Config=transfer(threads=32))
    only = None
    if cfg.get("only"):
        only = os.path.join(data, "only.txt")
        s3.download_file(name, f"runs/{run}/only.txt", only)
    state["inputs_s"] = round(time.time() - t0, 1)
    print(f"inputs in {state['inputs_s']} s", flush=True)
    g0, missed = geometry_new(geometry)[0], []

    env = {**os.environ, "CASSINI_DATA": archive, "CASSINI_GEOMETRY_CACHE": geometry,
           "CASSINI_INDEX_CACHE": os.path.join(WORK, "zip_index"), "CASSINI_SPICE_CACHE": os.path.join(WORK, "spice_cache"),
           "MPLBACKEND": "Agg", "FRAME_SERVER_QUIET": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    procs = cfg.get("procs") or os.cpu_count()
    shipper = Shipper(s3, name, run, cache, cfg.get("work_files", True))
    for phase in cfg["phases"]:
        state.update(state="building", phase=phase)
        p0 = time.time()
        cmd = [sys.executable, os.path.join(HERE, "prebuild.py"), phase, "--cache", cache, "--status", stat,
               "--procs", str(procs), "--balanced", "--live", "", "--max-load", "1e9", "--pause", "/nonexistent/pause"]
        rc = subprocess.call(cmd + (["--only", only] if only else []), cwd=REPO, env=env)
        done = {"phase": phase, "s": round(time.time() - p0, 1), "exit": rc}
        try:
            with open(os.path.join(stat, f"status-{phase}.json")) as fh:
                pb = json.load(fh)
            done.update(done=pb.get("done"), total=pb.get("total"), errors=pb.get("errors"), made_s=pb.get("made_s"))
        except (OSError, ValueError):
            pass
        state["phases_done"].append(done)
        _, state["geometry_misses"], missed = geometry_new(geometry, g0)
        print(f"{phase}: {done}, {state['geometry_misses']} frames not in the geometry cache so far", flush=True)
        shipper.ship(phase, time.time())
    state.update(state="shipping the last phase", phase=None)
    shipper.finish()
    with tempfile.TemporaryDirectory() as tmp:
        notes = os.path.join(tmp, "status-files.tar.gz")
        with tarfile.open(notes, "w:gz") as tf:
            tf.add(stat, arcname="status")
        s3.upload_file(notes, name, f"runs/{run}/status-files.tar.gz")
    manifest = {"run": run, "commit": cfg["commit"], "phases": state["phases_done"], "inputs_s": state["inputs_s"],
                "shards": shipper.shards, "totals": shipper.totals, "procs": procs, "cpu": os.cpu_count(),
                "geometry_misses": state.get("geometry_misses", 0), "geometry_missed": missed,
                "finished": time.time(), "took_s": round(time.time() - state["started"], 1)}
    put_json(s3, name, f"runs/{run}/manifest.json", manifest)
    state.update(state="done" if all(p["exit"] == 0 for p in state["phases_done"]) and "error" not in shipper.totals
                 else "done with errors")
    put_json(s3, name, f"runs/{run}/status.json", dict(state, updated=time.time(), shipped=shipper.totals))
    print(f"done: {json.dumps(shipper.totals)}", flush=True)


# ---------- on the Mini ----------

def upload_inputs(args):
    """The archive and the geometry cache into the bucket (each skipped when the bucket has it, same size and
    time): the geometry cache copied first through sqlite's backup, so a copy in use by a server is copied whole."""
    name, region = bucket()
    s3 = client("s3", region)
    with tempfile.TemporaryDirectory(dir=args.tmp) as tmp:
        snap = os.path.join(tmp, "geometry.sqlite")
        geometry = os.path.expanduser(args.geometry)
        changed = max(os.path.getmtime(p) for p in (geometry, geometry + "-wal") if os.path.exists(p))   # rows wait in the WAL
        src = sqlite3.connect(geometry)
        dst = sqlite3.connect(snap)
        src.backup(dst)
        dst.close()
        src.close()
        for path, key, stamp in ((os.path.expanduser(args.archive), INPUTS["archive"], None),
                                 (snap, INPUTS["geometry"], changed)):
            size, stamp = os.path.getsize(path), str(int(stamp or os.path.getmtime(path)))
            h = head(s3, name, key)
            if h and h["ContentLength"] == size and h.get("Metadata", {}).get("mtime") == stamp:
                print(f"{key}: already there ({size / 1e9:.1f} GB)")
                continue
            t0, sent = time.time(), [0, 0]

            def progress(n, size=size, t0=t0, sent=sent):
                sent[0] += n
                if time.time() - sent[1] > 30:
                    sent[1] = time.time()
                    rate = sent[0] / max(1e-6, time.time() - t0)
                    print(f"  {key}: {sent[0] / 1e9:.1f}/{size / 1e9:.1f} GB, {rate * 8 / 1e6:.0f} Mbit/s, "
                          f"~{(size - sent[0]) / max(rate, 1) / 60:.0f} min left", flush=True)
            s3.upload_file(path, name, key, Config=transfer(chunk_mb=256, threads=8), Callback=progress,
                           ExtraArgs={"Metadata": {"mtime": stamp}})
            print(f"{key}: {size / 1e9:.1f} GB in {(time.time() - t0) / 60:.1f} min", flush=True)


def safe_members(tf):
    """The tar's regular files with plain relative names (never absolute, never up a folder, never a link)."""
    for m in tf:
        if not m.isfile():
            continue
        parts = m.name.split("/")
        if m.name.startswith("/") or ".." in parts or not m.name:
            raise ValueError(f"unsafe name in shard: {m.name}")
        yield m


def compare_file(new, live):
    """'same' (bytes), 'pixels' (other bytes, the same pixels), or the largest mean and centre difference found
    (rebuild_bench.picture_stats) for a picture whose pixels differ."""
    with open(new, "rb") as a, open(live, "rb") as b:
        if a.read() == b.read():
            return "same"
    if not new.endswith((".webp", ".png")):
        return "differs"
    from rebuild_bench import picture_stats
    p, q = picture_stats(new), picture_stats(live)
    if p[0] == q[0]:
        return "pixels"
    return {"mean": round(abs(p[2] - q[2]), 4), "centre": round(max(abs(p[4] - q[4]), abs(p[5] - q[5])), 3)}


def link(path, target):
    """path made a symlink to target, in one step (a dangling link there replaced), as the sweeper makes them."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".link"
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, path)


def land(to, work_to, rel):
    """The working file work_to/rel shown at to/rel the way the Mini's sweeper lays them out
    (~/server/cache/cassini-prebuild-sweep.py): a pass's filters-level/ one link to its folder in work_to, a tile's
    picture a link of its own beside its report, which stays a real file in to. Links are absolute."""
    parts = rel.split("/")
    if "filters-level" in parts[:-1]:
        k = parts.index("filters-level") + 1
        folder = os.path.join(to, *parts[:k])
        if not os.path.lexists(folder):
            link(folder, os.path.abspath(os.path.join(work_to, *parts[:k])))
    if not os.path.exists(os.path.join(to, rel)):   # a tile's picture, or a filters-level/ that is a real folder
        link(os.path.join(to, rel), os.path.abspath(os.path.join(work_to, rel)))


def fetch(args):
    """A run's shards into --to (served) and --work-to (working files; default --to), each checked against its
    hash and unpacked file by file, a file already there left as it is: the served ones first, then the working
    files (--no-work: none). With a --work-to of its own, each working file shows in --to through a symlink, as the
    Mini's sweeper leaves them (land). --follow: shards as the machine ships them, until it is done. --compare: every
    file against the live cache's of the same name (same bytes, same pixels, or how far apart), a report at the end."""
    name, region = bucket()
    s3 = client("s3", region)
    to = os.path.expanduser(args.to)
    work_to = os.path.expanduser(args.work_to or args.to)
    for d in (to, work_to):   # an unmounted disk (the LaCie image after a reboot) would be made a folder on the SSD
        volume = os.sep.join(os.path.abspath(d).split(os.sep)[:3])
        if volume.startswith("/Volumes/") and not os.path.ismount(volume):
            sys.exit(f"{volume} is not mounted")
    os.makedirs(to, exist_ok=True)
    os.makedirs(work_to, exist_ok=True)
    if os.path.abspath(work_to) != os.path.abspath(to) and not args.no_work:
        probe = os.path.join(to, ".cloud-fetch-link")
        try:
            if os.path.lexists(probe):
                os.remove(probe)
            os.symlink(os.path.abspath(work_to), probe)
            os.remove(probe)
        except OSError as e:
            sys.exit(f"{to} cannot hold links to the working files ({e.strerror}): exFAT cannot; put --to on APFS")
    tmp = os.path.expanduser(args.tmp or os.path.join(to, ".cloud-fetch"))
    os.makedirs(tmp, exist_ok=True)
    state_path = os.path.join(tmp, f"{args.run}.json")
    done = json.load(open(state_path)) if os.path.exists(state_path) else {}
    report = {"same": 0, "pixels": 0, "differs": 0, "new": 0, "kept": 0, "worst": []}
    written = [0, time.time()]   # bytes written and since when (--max-mb-s)
    while True:
        manifest = get_json(s3, name, f"runs/{args.run}/manifest.json")
        if manifest:
            shards = manifest["shards"]
        else:
            listed = s3.list_objects_v2(Bucket=name, Prefix=f"runs/{args.run}/out/").get("Contents", [])
            shards = [{"key": o["Key"], "kind": os.path.basename(o["Key"]).split("-")[0], "bytes": o["Size"]} for o in listed]
        todo = [s for s in shards if s["key"] not in done and (s["kind"] == "served" or not args.no_work)]
        todo.sort(key=lambda s: (s["kind"] != "served", s["key"]))
        for s in todo:
            dest = to if s["kind"] == "served" else work_to
            free = shutil.disk_usage(dest).free / 1e9
            if free - 2 * s["bytes"] / 1e9 < args.min_free:
                sys.exit(f"stopping: {dest} has {free:.0f} GB free, and the next shard needs "
                         f"{2 * s['bytes'] / 1e9:.1f} GB above the {args.min_free:g} GB floor")
            path = os.path.join(tmp, os.path.basename(s["key"]))
            t0 = time.time()
            s3.download_file(name, s["key"], path, Config=transfer(threads=8))
            want = s.get("sha256") or head(s3, name, s["key"])["Metadata"].get("sha256")
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for block in iter(lambda: fh.read(8 << 20), b""):
                    h.update(block)
            if want and h.hexdigest() != want:
                os.remove(path)
                sys.exit(f"{s['key']}: hash differs from the machine's; run fetch again")
            linked = s["kind"] != "served" and os.path.abspath(work_to) != os.path.abspath(to)
            n = kept = 0
            with tarfile.open(path) as tf:
                for m in safe_members(tf):
                    out = os.path.join(dest, m.name)
                    if os.path.exists(os.path.join(to, m.name) if linked else out):   # where the server looks
                        kept += 1
                        continue
                    if not os.path.exists(out):   # (linked: there from a fetch stopped before its link)
                        os.makedirs(os.path.dirname(out), exist_ok=True)
                        part = out + ".fetch.part"
                        with tf.extractfile(m) as src, open(part, "wb") as fh:
                            shutil.copyfileobj(src, fh)
                        os.replace(part, out)
                        if args.max_mb_s:   # (the LaCie image hung once under heavy writes: the sweeper's rsync goes at 50)
                            written[0] += m.size
                            time.sleep(max(0.0, written[0] / (args.max_mb_s * 1e6) - (time.time() - written[1])))
                    if linked:
                        land(to, work_to, m.name)
                    n += 1
                    if args.compare and s["kind"] == "served":
                        live = os.path.join(os.path.expanduser(args.compare), m.name)
                        if not os.path.exists(live):
                            report["new"] += 1
                            continue
                        r = compare_file(out, live)
                        if isinstance(r, dict):
                            report["differs"] += 1
                            report["worst"] = sorted(report["worst"] + [dict(r, file=m.name)],
                                                     key=lambda x: -x["mean"])[:20]
                        else:
                            report[r] += 1
            report["kept"] += kept
            os.remove(path)
            done[s["key"]] = {"files": n, "kept": kept, "s": round(time.time() - t0, 1)}
            with open(state_path, "w") as fh:
                json.dump(done, fh)
            print(f"{s['key']}: {n:,} files ({kept:,} already there) in {time.time() - t0:.0f} s, "
                  f"{s['bytes'] / 1e9:.2f} GB", flush=True)
        if manifest or not args.follow:
            break
        beat = get_json(s3, name, f"runs/{args.run}/status.json") or {}
        if (beat.get("state") or "").startswith("failed") or time.time() - beat.get("updated", time.time()) > 900:
            print(f"the machine stopped ({beat.get('state')}, no manifest): fetched what it shipped")
            break
        time.sleep(60)
    if args.compare:
        with open(os.path.join(tmp, f"{args.run}-compare.json"), "w") as fh:
            json.dump(report, fh, indent=1)
        print(f"against {args.compare}: {report['same']:,} the same bytes, {report['pixels']:,} other bytes with the "
              f"same pixels, {report['differs']:,} with other pixels "
              f"(worst mean {report['worst'][0]['mean'] if report['worst'] else 0} gray levels), "
              f"{report['new']:,} not in the live cache")
    print(f"fetched {len(done)} shards into {to}" + (f" and {work_to}" if work_to != to else ""))
    if manifest and manifest.get("geometry_misses"):
        print(f"warning: {manifest['geometry_misses']:,} frames were not in the geometry cache, so the machine could not "
              f"centre them (first: {', '.join(manifest['geometry_missed'][:5])})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("setup")
    p.add_argument("--region", choices=REGIONS)
    p.add_argument("--vcpus", type=int, default=64, help="the quota to ask for (one 64-core machine at a time)")
    p.add_argument("--keep-days", type=int, default=21, help="runs' files are deleted this many days after a run")
    p = sub.add_parser("creds")
    p.add_argument("--hours", type=float, default=12)
    p = sub.add_parser("launch")
    p.add_argument("--phases", help="comma separated (default: every phase, in prebuild's order)")
    p.add_argument("--only", help="file of frame ids: only the items using them (prebuild --only)")
    p.add_argument("--commit", default="origin/main", help="the code to build with: what the Mini serves")
    p.add_argument("--types", help=f"machine types to try, in order (default {','.join(TYPES)})")
    p.add_argument("--procs", type=int, default=0, help="processes (default: one a core)")
    p.add_argument("--disk", type=int, default=DISK_GB, help="GB of disk")
    p.add_argument("--max-hours", type=float, default=6, help="the machine ends itself after this long, whatever happens")
    p.add_argument("--on-demand", action="store_true", help="a regular machine, not spot (dearer, never taken back)")
    p.add_argument("--served-only", action="store_true", help="ship what is served only, not the working files")
    p.add_argument("--parallel", action="store_true", help="even while another build machine runs")
    p.add_argument("--run", help="the run's name (default: time and commit)")
    p.add_argument("--image", help="the machine image (default: the newest Amazon Linux 2023)")
    p = sub.add_parser("status")
    p.add_argument("--run")
    p = sub.add_parser("stop")
    p.add_argument("--run", required=True)
    p = sub.add_parser("work")
    p.add_argument("--run", required=True)
    p.add_argument("--bucket")
    p = sub.add_parser("upload-inputs")
    p.add_argument("--archive", required=True)
    p.add_argument("--geometry", required=True)
    p.add_argument("--tmp", help="folder for the geometry cache's copy (default: the system's)")
    p = sub.add_parser("fetch")
    p.add_argument("--run", required=True)
    p.add_argument("--to", required=True, help="the cache folder the served files go into")
    p.add_argument("--work-to", help="where the working files go (default --to)")
    p.add_argument("--no-work", action="store_true", help="only the served files")
    p.add_argument("--tmp", help="folder for shards on their way (default <to>/.cloud-fetch)")
    p.add_argument("--min-free", type=float, default=50, help="GB the disks keep free")
    p.add_argument("--follow", action="store_true", help="fetch shards as they are shipped, until the run is done")
    p.add_argument("--compare", help="a live cache to compare every served file with")
    p.add_argument("--max-mb-s", type=float, help="write at most this many MB a second (into the LaCie image: 50, as the sweeper)")
    args = ap.parse_args()
    {"check": check, "setup": setup, "creds": creds, "launch": launch, "status": status, "stop": stop, "work": work,
     "upload-inputs": upload_inputs, "fetch": fetch}[args.cmd](args)


if __name__ == "__main__":
    main()
