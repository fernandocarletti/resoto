from resoto_plugin_aws.resource.ec2 import (
    AwsEc2Instance,
    AwsEc2KeyPair,
    AwsEc2Volume,
    AwsEc2NetworkAcl,
    AwsEc2InstanceType,
    AwsEc2ReservedInstances,
    AwsEc2ElasticIp,
    AwsEc2NetworkInterface,
    AwsEc2Vpc,
    AwsEc2Subnet,
    AwsEc2SecurityGroup,
    AwsEc2NatGateway,
    AwsEc2InternetGateway,
    AwsEc2Snapshot,
    AwsEc2VpcPeeringConnection,
    AwsEc2VpcEndpoint,
    AwsEc2RouteTable,
)
from test.resources import round_trip_for, build_graph, check_single_node


def test_instance_types() -> None:
    builder = build_graph(AwsEc2InstanceType)
    for it in builder.global_instance_types.values():
        it.connect_in_graph(builder, {})
        check_single_node(it)


def test_reserved_instances() -> None:
    round_trip_for(AwsEc2ReservedInstances)


def test_volumes() -> None:
    round_trip_for(AwsEc2Volume)


def test_snapshots() -> None:
    round_trip_for(AwsEc2Snapshot)


def test_keypair() -> None:
    round_trip_for(AwsEc2KeyPair)


def test_instance() -> None:
    round_trip_for(AwsEc2Instance)


def test_network_acl() -> None:
    round_trip_for(AwsEc2NetworkAcl)


def test_elastic_ips() -> None:
    round_trip_for(AwsEc2ElasticIp)


def test_network_interfaces() -> None:
    round_trip_for(AwsEc2NetworkInterface)


def test_vpcs() -> None:
    round_trip_for(AwsEc2Vpc)


def test_vpc_peering_connections() -> None:
    round_trip_for(AwsEc2VpcPeeringConnection)


def test_vpc_endpoints() -> None:
    round_trip_for(AwsEc2VpcEndpoint)


def test_subnets() -> None:
    round_trip_for(AwsEc2Subnet)


def test_route_table() -> None:
    round_trip_for(AwsEc2RouteTable)


def test_security_groups() -> None:
    round_trip_for(AwsEc2SecurityGroup)


def test_nat_gateways() -> None:
    round_trip_for(AwsEc2NatGateway)


def test_internet_gateways() -> None:
    round_trip_for(AwsEc2InternetGateway)
