import logging

import botocore.exceptions
import multiprocessing
import resotolib.proc
import resotolib.logger
from resotolib.logger import log, setup_logger
from concurrent import futures
from resotolib.args import ArgumentParser
from resotolib.args import Namespace
from resotolib.config import Config, RunningConfig
from resotolib.graph import Graph
from resotolib.utils import log_runtime
from resotolib.baseplugin import BaseCollectorPlugin
from .config import AwsConfig
from .utils import aws_session
from .resources import AWSAccount
from .accountcollector import AWSAccountCollector
from prometheus_client import Summary, Counter
from typing import List, Optional


logging.getLogger("boto").setLevel(logging.CRITICAL)

metrics_collect = Summary("resoto_plugin_aws_collect_seconds", "Time it took the collect() method")
metrics_unhandled_account_exceptions = Counter(
    "resoto_plugin_aws_unhandled_account_exceptions_total",
    "Unhandled AWS Plugin Account Exceptions",
    ["account"],
)


class AWSCollectorPlugin(BaseCollectorPlugin):
    cloud = "aws"

    def __init__(self) -> None:
        super().__init__()
        self.__regions: List[str] = []

    @staticmethod
    def add_config(cfg: Config) -> None:
        cfg.add_config(AwsConfig)

    @metrics_collect.time()  # type: ignore
    def collect(self) -> None:
        log.debug("plugin: AWS collecting resources")

        accounts = get_accounts()
        if len(accounts) == 0:
            log.error("No accounts found")
            return
        for account in accounts:
            add_str = ""
            if account.role:
                add_str += f" role {account.role}"
            if account.profile:
                add_str += f" profile {account.profile}"
            log.debug(f"Found {account.rtdname}{add_str}")

        max_workers = len(accounts) if len(accounts) < Config.aws.account_pool_size else Config.aws.account_pool_size
        pool_args = {"max_workers": max_workers}
        if Config.aws.fork_process:
            pool_args["mp_context"] = multiprocessing.get_context("spawn")
            pool_args["initializer"] = resotolib.proc.initializer
            pool_executor = futures.ProcessPoolExecutor
        else:
            pool_executor = futures.ThreadPoolExecutor  # type: ignore

        with pool_executor(**pool_args) as executor:
            wait_for = [
                executor.submit(
                    collect_account,
                    account,
                    self.regions(profile=account.profile),
                    ArgumentParser.args,
                    Config.running_config,
                )
                for account in accounts
            ]
            for future in futures.as_completed(wait_for):
                account_graph = future.result()
                if not isinstance(account_graph, Graph):
                    log.debug(f"Skipping account graph of invalid type {type(account_graph)}")
                    continue
                self.graph.merge(account_graph)

    def regions(self, profile: Optional[str] = None) -> List[str]:
        if len(self.__regions) == 0:
            if not Config.aws.region or (isinstance(Config.aws.region, list) and len(Config.aws.region) == 0):
                log.debug("AWS region not specified, assuming all regions")
                self.__regions = all_regions(profile=profile)
            else:
                self.__regions = list(Config.aws.region)
        return self.__regions


def authenticated(account: AWSAccount) -> bool:
    try:
        log.debug(f"AWS testing credentials for {account.rtdname}")
        session = aws_session(account.id, account.role, account.profile)
        _ = session.client("sts").get_caller_identity().get("Account")
    except botocore.exceptions.NoCredentialsError:
        log.error(f"No AWS credentials found for {account.rtdname}")
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "AuthFailure":
            log.error(f"AWS was unable to validate the provided access credentials for {account.rtdname}")
        elif e.response["Error"]["Code"] == "InvalidClientTokenId":
            log.error(f"AWS was unable to validate the provided security token for {account.rtdname}")
        elif e.response["Error"]["Code"] == "ExpiredToken":
            log.error(f"AWS security token included in the request is expired for {account.rtdname}")
        elif e.response["Error"]["Code"] == "AccessDenied":
            log.error(f"AWS denied access to {account.rtdname}")
        else:
            raise
        return False
    return True


def current_account_id(profile: Optional[str] = None) -> str:
    session = aws_session(profile=profile)
    return session.client("sts").get_caller_identity().get("Account")  # type: ignore


def get_accounts() -> List[AWSAccount]:
    accounts = []
    profiles = [None]

    if Config.aws.assume_current and not Config.aws.do_not_scrape_current:
        raise ValueError(
            "You specified assume_current but not do_not_scrape_current! "
            "This will result in the same account being collected twice and is likely not what you want."
        )

    if isinstance(Config.aws.profiles, list) and len(Config.aws.profiles) > 0:
        log.debug("Using specified AWS profiles")
        profiles = Config.aws.profiles
        if Config.aws.account and len(Config.aws.profiles) > 1:
            raise ValueError(
                "You specified both a list of accounts and more than one profile! "
                "This will result in the attempt to collect the same accounts for "
                "every profile and is likely not what you want."
            )

    for profile in profiles:
        if profile is not None:
            log.debug(f"Finding accounts for profile {profile}")

        try:
            if Config.aws.role and Config.aws.scrape_org:
                log.debug("Role and scrape_org are both set")
                accounts.extend(
                    [
                        AWSAccount(id=aws_account_id, role=Config.aws.role, profile=profile)
                        for aws_account_id in get_org_accounts(
                            filter_current_account=not Config.aws.assume_current, profile=profile
                        )
                        if aws_account_id not in Config.aws.scrape_exclude_account
                    ]
                )
                if not Config.aws.do_not_scrape_current:
                    accounts.append(AWSAccount(id=current_account_id(profile=profile)))
            elif Config.aws.role and Config.aws.account:
                log.debug("Both, role and list of accounts specified")
                accounts.extend(
                    [
                        AWSAccount(id=aws_account_id, role=Config.aws.role, profile=profile)
                        for aws_account_id in Config.aws.account
                    ]
                )
            else:
                accounts.extend([AWSAccount(id=current_account_id(profile=profile), profile=profile)])
        except botocore.exceptions.NoCredentialsError:
            log.error(f"No AWS credentials found for {profile}")
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "AuthFailure":
                log.error(f"AWS was unable to validate the provided access credentials for {profile}")
            elif e.response["Error"]["Code"] == "InvalidClientTokenId":
                log.error(f"AWS was unable to validate the provided security token for {profile}")
            elif e.response["Error"]["Code"] == "ExpiredToken":
                log.error(f"AWS security token included in the request is expired for {profile}")
            elif e.response["Error"]["Code"] == "AccessDenied":
                log.error(f"AWS denied access for {profile}")
            else:
                raise

    return accounts


def get_org_accounts(filter_current_account: bool = False, profile: Optional[str] = None) -> List[str]:
    session = aws_session(profile=profile)
    client = session.client("organizations")
    accounts = []
    try:
        response = client.list_accounts()
        accounts = response.get("Accounts", [])
        while response.get("NextToken") is not None:
            response = client.list_accounts(NextToken=response["NextToken"])
            accounts.extend(response.get("Accounts", []))
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "AccessDeniedException":
            log.error("AWS error - missing permissions to list organization accounts")
        else:
            raise
    filter_account_id = current_account_id(profile=profile) if filter_current_account else -1
    accounts = [aws_account["Id"] for aws_account in accounts if aws_account["Id"] != filter_account_id]
    for account in accounts:
        log.debug(f"AWS found org account {account}")
    log.info(f"AWS found a total of {len(accounts)} org accounts")
    return accounts


def all_regions(profile: Optional[str] = None) -> List[str]:
    session = aws_session(profile=profile)
    ec2 = session.client("ec2", region_name="us-east-1")
    regions = ec2.describe_regions()
    return [r["RegionName"] for r in regions["Regions"]]


@log_runtime  # type: ignore
def collect_account(
    account: AWSAccount,
    regions: List[str],
    args: Namespace,
    running_config: RunningConfig,
) -> Optional[Graph]:
    collector_name = f"aws_{account.id}"
    resotolib.proc.set_thread_name(collector_name)

    if args is not None:
        ArgumentParser.args = args
        setup_logger("resotoworker-aws")
    if running_config is not None:
        Config.running_config.apply(running_config)

    if not authenticated(account):
        log.error(f"Skipping {account.rtdname} due to authentication failure")
        return None

    log.debug(f"Starting new collect process for account {account.dname}")

    aac = AWSAccountCollector(regions, account)
    try:
        aac.collect()
    except botocore.exceptions.ClientError as e:
        log.exception(f"An AWS {e.response['Error']['Code']} error occurred while collecting account {account.dname}")
        metrics_unhandled_account_exceptions.labels(account=account.dname).inc()
        return None
    except Exception:
        log.exception(f"An unhandled error occurred while collecting AWS account {account.dname}")
        metrics_unhandled_account_exceptions.labels(account=account.dname).inc()
        return None

    return aac.graph  # type: ignore
