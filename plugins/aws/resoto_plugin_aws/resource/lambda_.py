import re
from typing import ClassVar, Dict, Optional, List, Type

from attrs import define, field

from resoto_plugin_aws.resource.base import AwsResource, GraphBuilder, AwsApiSpec
from resoto_plugin_aws.resource.ec2 import AwsEc2Subnet, AwsEc2SecurityGroup, AwsEc2Vpc
from resotolib.baseresources import (  # noqa: F401
    BaseCertificate,
    BasePolicy,
    BaseGroup,
    BaseAccount,
    BaseAccessKey,
    BaseUser,
    BaseServerlessFunction,
    ModelReference,
)
from resotolib.json_bender import Bender, S, Bend, ForallBend, F
from resotolib.types import Json


@define(eq=False, slots=False)
class AwsLambdaEnvironmentError:
    kind: ClassVar[str] = "aws_lambda_environment_error"
    mapping: ClassVar[Dict[str, Bender]] = {"error_code": S("ErrorCode"), "message": S("Message")}
    error_code: Optional[str] = field(default=None)
    message: Optional[str] = field(default=None)


@define(eq=False, slots=False)
class AwsLambdaEnvironmentResponse:
    kind: ClassVar[str] = "aws_lambda_environment_response"
    mapping: ClassVar[Dict[str, Bender]] = {
        "variables": S("Variables"),
        "error": S("Error") >> Bend(AwsLambdaEnvironmentError.mapping),
    }
    variables: Optional[Dict[str, str]] = field(default=None)
    error: Optional[AwsLambdaEnvironmentError] = field(default=None)


@define(eq=False, slots=False)
class AwsLambdaLayer:
    kind: ClassVar[str] = "aws_lambda_layer"
    mapping: ClassVar[Dict[str, Bender]] = {
        "arn": S("Arn"),
        "code_size": S("CodeSize"),
        "signing_profile_version_arn": S("SigningProfileVersionArn"),
        "signing_job_arn": S("SigningJobArn"),
    }
    arn: Optional[str] = field(default=None)
    code_size: Optional[int] = field(default=None)
    signing_profile_version_arn: Optional[str] = field(default=None)
    signing_job_arn: Optional[str] = field(default=None)


@define(eq=False, slots=False)
class AwsLambdaFileSystemConfig:
    kind: ClassVar[str] = "aws_lambda_file_system_config"
    mapping: ClassVar[Dict[str, Bender]] = {"arn": S("Arn"), "local_mount_path": S("LocalMountPath")}
    arn: Optional[str] = field(default=None)
    local_mount_path: Optional[str] = field(default=None)


@define(eq=False, slots=False)
class AwsLambdaImageConfig:
    kind: ClassVar[str] = "aws_lambda_image_config"
    mapping: ClassVar[Dict[str, Bender]] = {
        "entry_point": S("EntryPoint", default=[]),
        "command": S("Command", default=[]),
        "working_directory": S("WorkingDirectory"),
    }
    entry_point: List[str] = field(factory=list)
    command: List[str] = field(factory=list)
    working_directory: Optional[str] = field(default=None)


@define(eq=False, slots=False)
class AwsLambdaImageConfigError:
    kind: ClassVar[str] = "aws_lambda_image_config_error"
    mapping: ClassVar[Dict[str, Bender]] = {"error_code": S("ErrorCode"), "message": S("Message")}
    error_code: Optional[str] = field(default=None)
    message: Optional[str] = field(default=None)


@define(eq=False, slots=False)
class AwsLambdaImageConfigResponse:
    kind: ClassVar[str] = "aws_lambda_image_config_response"
    mapping: ClassVar[Dict[str, Bender]] = {
        "image_config": S("ImageConfig") >> Bend(AwsLambdaImageConfig.mapping),
        "error": S("Error") >> Bend(AwsLambdaImageConfigError.mapping),
    }
    image_config: Optional[AwsLambdaImageConfig] = field(default=None)
    error: Optional[AwsLambdaImageConfigError] = field(default=None)


@define(eq=False, slots=False)
class AwsLambdaFunction(AwsResource, BaseServerlessFunction):
    kind: ClassVar[str] = "aws_lambda_function"
    api_spec: ClassVar[AwsApiSpec] = AwsApiSpec("lambda", "list-functions", "Functions")
    reference_kinds: ClassVar[ModelReference] = {
        "predecessors": {"default": ["aws_vpc", "aws_ec2_subnet", "aws_ec2_security_group"]},
        "successors": {"delete": ["aws_vpc", "aws_ec2_subnet", "aws_ec2_security_group"]},
    }
    mapping: ClassVar[Dict[str, Bender]] = {
        "id": S("FunctionName"),
        "name": S("FunctionName"),
        "mtime": S("LastModified") >> F(lambda x: re.sub(r"(\d\d)(\d\d)$", "\\1:\\2", x)),  # time zone is without colon
        "arn": S("FunctionArn"),
        "function_runtime": S("Runtime"),
        "function_role": S("Role"),
        "function_handler": S("Handler"),
        "function_code_size": S("CodeSize"),
        "function_description": S("Description"),
        "function_timeout": S("Timeout"),
        "function_memory_size": S("MemorySize"),
        "function_code_sha256": S("CodeSha256"),
        "function_version": S("Version"),
        "function_dead_letter_config": S("DeadLetterConfig", "TargetArn"),
        "function_environment": S("Environment") >> Bend(AwsLambdaEnvironmentResponse.mapping),
        "function_kms_key_arn": S("KMSKeyArn"),
        "function_tracing_config": S("TracingConfig", "Mode"),
        "function_master_arn": S("MasterArn"),
        "function_revision_id": S("RevisionId"),
        "function_layers": S("Layers", default=[]) >> ForallBend(AwsLambdaLayer.mapping),
        "function_state": S("State"),
        "function_state_reason": S("StateReason"),
        "function_state_reason_code": S("StateReasonCode"),
        "function_last_update_status": S("LastUpdateStatus"),
        "function_last_update_status_reason": S("LastUpdateStatusReason"),
        "function_last_update_status_reason_code": S("LastUpdateStatusReasonCode"),
        "function_file_system_configs": S("FileSystemConfigs", default=[])
        >> ForallBend(AwsLambdaFileSystemConfig.mapping),
        "function_package_type": S("PackageType"),
        "function_image_config_response": S("ImageConfigResponse") >> Bend(AwsLambdaImageConfigResponse.mapping),
        "function_signing_profile_version_arn": S("SigningProfileVersionArn"),
        "function_signing_job_arn": S("SigningJobArn"),
        "function_architectures": S("Architectures", default=[]),
        "function_ephemeral_storage": S("EphemeralStorage", "Size"),
    }
    function_runtime: Optional[str] = field(default=None)
    function_role: Optional[str] = field(default=None)
    function_handler: Optional[str] = field(default=None)
    function_code_size: Optional[int] = field(default=None)
    function_description: Optional[str] = field(default=None)
    function_timeout: Optional[int] = field(default=None)
    function_memory_size: Optional[int] = field(default=None)
    function_code_sha256: Optional[str] = field(default=None)
    function_version: Optional[str] = field(default=None)
    function_dead_letter_config: Optional[str] = field(default=None)
    function_environment: Optional[AwsLambdaEnvironmentResponse] = field(default=None)
    function_kms_key_arn: Optional[str] = field(default=None)
    function_tracing_config: Optional[str] = field(default=None)
    function_master_arn: Optional[str] = field(default=None)
    function_revision_id: Optional[str] = field(default=None)
    function_layers: List[AwsLambdaLayer] = field(factory=list)
    function_state: Optional[str] = field(default=None)
    function_state_reason: Optional[str] = field(default=None)
    function_state_reason_code: Optional[str] = field(default=None)
    function_last_update_status: Optional[str] = field(default=None)
    function_last_update_status_reason: Optional[str] = field(default=None)
    function_last_update_status_reason_code: Optional[str] = field(default=None)
    function_file_system_configs: List[AwsLambdaFileSystemConfig] = field(factory=list)
    function_package_type: Optional[str] = field(default=None)
    function_image_config_response: Optional[AwsLambdaImageConfigResponse] = field(default=None)
    function_signing_profile_version_arn: Optional[str] = field(default=None)
    function_signing_job_arn: Optional[str] = field(default=None)
    function_architectures: List[str] = field(factory=list)
    function_ephemeral_storage: Optional[int] = field(default=None)

    def connect_in_graph(self, builder: GraphBuilder, source: Json) -> None:
        if vpc_config := source.get("VpcConfig"):
            if vpc_id := vpc_config.get("VpcId"):
                builder.dependant_node(self, reverse=True, clazz=AwsEc2Vpc, id=vpc_id)
            for subnet_id in vpc_config.get("SubnetIds", []):
                builder.dependant_node(self, reverse=True, clazz=AwsEc2Subnet, id=subnet_id)
            for security_group_id in vpc_config.get("SecurityGroupIds", []):
                builder.dependant_node(self, reverse=True, clazz=AwsEc2SecurityGroup, id=security_group_id)


resources: List[Type[AwsResource]] = [AwsLambdaFunction]
