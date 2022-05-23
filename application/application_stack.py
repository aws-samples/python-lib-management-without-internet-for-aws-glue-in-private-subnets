from aws_cdk import (
    aws_ec2 as ec2,
    aws_ssm as ssm,
    aws_codeartifact as codeartifact,
    aws_stepfunctions as sfn,
    aws_glue_alpha as glue,
    aws_iam as iam,
    aws_s3 as s3,
    aws_logs as logs,
    aws_s3_deployment as s3_deployment,
    Aspects,Stack,RemovalPolicy,Aws,Duration,CfnOutput
    
)
from constructs import Construct

import json,os

from cdk_nag import ( AwsSolutionsChecks, NagSuppressions )

class ApplicationStack(Stack):
  
  def create_pypi_repo(self):
    artifact_repo = codeartifact.CfnRepository(self,
                                               id=self.pypi_repo_name,
                                               domain_name=self.domain_name,
                                               repository_name=self.pypi_repo_name,
                                               external_connections=["public:pypi"],
                                               description="Provides PyPI artifacts from PyPA.")
    return artifact_repo
  
  def create_code_repo(self):
    code_repo = codeartifact.CfnRepository(self,
                                            id=self.repo_name,
                                            domain_name=self.domain_name,
                                            repository_name=self.repo_name,
                                            upstreams=[self.pypi_repo_name],
                                            description="Internal python package repository.")
    return code_repo



  def __init__(self, scope: Construct, construct_id: str, cidr_block: str,**kwargs) -> None:
    super().__init__(scope, construct_id, **kwargs)

    ############################################
    ##
    ## CDK Nag - https://pypi.org/project/cdk-nag/
    ##           https://github.com/cdklabs/cdk-nag
    ##
    ## CDK Nag Checks for AWS Engagement Solutions Secuirty Rules:
    ##   https://github.com/cdklabs/cdk-nag/blob/main/RULES.md#awssolutions
    ## Also checks for:
    ##   HIPAA Security
    ##   NIST 800-53 rev 4
    ##   NIST 800-53 rev 5
    ##
    ############################################
    Aspects.of(self).add(AwsSolutionsChecks())
    ##
    ## Supressed Errors
    ##
    NagSuppressions.add_stack_suppressions(self, [{"id":"AwsSolutions-S1",   "reason":"TODO: Set *server_access_logs_bucket* and *server_access_logs_prefix* to enable server access logging."}])
    NagSuppressions.add_stack_suppressions(self, [{"id":"AwsSolutions-IAM4", "reason":"TODO: Stop using AWS managed policies."}])
    NagSuppressions.add_stack_suppressions(self, [{"id":"AwsSolutions-IAM5", "reason":"TODO: Remove Wildcards in IAM roles."}])
    NagSuppressions.add_stack_suppressions(self, [{"id":"AwsSolutions-SF2", "reason":"TODO: Set the X-Ray Tracing on the Step Function."}])
    NagSuppressions.add_stack_suppressions(self, [{"id":"AwsSolutions-SF1", "reason":"TODO: Set the Step Function CloudWatch Logs log events to 'ALL' "}])

    ## Variable Initialization
    cdk_account_id:str = os.environ["CDK_DEFAULT_ACCOUNT"] 

    # The code that defines your stack goes here

    ########################################
    ##
    ## VPC
    ##
    #########################################
    
    self.vpc = ec2.Vpc(self, 'enterprise-repo-vpc',
      gateway_endpoints={
        "S3": ec2.GatewayVpcEndpointOptions(
          service=ec2.GatewayVpcEndpointAwsService.S3
        )
      },
      vpc_name = 'enterprise-repo-vpc',
      cidr = cidr_block,
      max_azs = 1,
      enable_dns_hostnames = True,
      enable_dns_support = True, 
      subnet_configuration=[
        ec2.SubnetConfiguration(
          name = 'Enterprise-Repo-Private-',
          subnet_type = ec2.SubnetType.PRIVATE_ISOLATED,
          cidr_mask = 26
        )
      ],
    )
    priv_subnets = [subnet.subnet_id for subnet in self.vpc.private_subnets]

    count = 1
    for psub in priv_subnets: 
      ssm.StringParameter(self, 'enterprise-repo-private-subnet-'+ str(count),
        string_value = psub,
        parameter_name = '/enterprise-repo/private-subnet-'+str(count)
        )
      count += 1 

    log_group = logs.LogGroup(self, "enterprise-repo-log-group")

    role = iam.Role(self, "enterprise-repo-vpc-flow-log-role",
        assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com")
    )

    ec2.FlowLog(self, "enterprise-repo-vpc-flow-log",
        resource_type=ec2.FlowLogResourceType.from_vpc(self.vpc),
        destination=ec2.FlowLogDestination.to_cloud_watch_logs(log_group, role)
    )

    ########################################
    ##
    ## S3 Bucket
    ##
    #########################################

    bucket = s3.Bucket(self,
                       "enterprise-repo-bucket",
                       bucket_name="codeartifactblog-"+str(cdk_account_id[-5:])+"-"+Aws.REGION,
                       auto_delete_objects= True,
                       removal_policy=RemovalPolicy.DESTROY,
                       block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                       encryption= s3.BucketEncryption.S3_MANAGED)

    s3_deployment.BucketDeployment(self,
                                   "enterprise-repo-bucket-deployment",
                                   sources=[s3_deployment.Source.asset("./scripts/s3")],
                                   destination_bucket=bucket,
                                   destination_key_prefix="data")

    ########################################
    ##
    ## Code Artifact VPC InterFace Endpoint
    ##
    #########################################

    self.vpc.add_interface_endpoint("CodeArtifactEndPoint",
                                    service=ec2.InterfaceVpcEndpointService(f'com.amazonaws.{Aws.REGION}.codeartifact.api'),
                                    subnets=ec2.SubnetType.PRIVATE_ISOLATED)

    self.vpc.add_interface_endpoint("CodeArtifactRepositoriesEndPoint",
                                    service=ec2.InterfaceVpcEndpointService(f'com.amazonaws.{Aws.REGION}.codeartifact.repositories'),
                                    subnets=ec2.SubnetType.PRIVATE_ISOLATED,
                                    private_dns_enabled=True)

    self.vpc.add_interface_endpoint("GlueRepositoriesEndPoint",
                                    service=ec2.InterfaceVpcEndpointService(f'com.amazonaws.{Aws.REGION}.glue'),
                                    subnets=ec2.SubnetType.PRIVATE_ISOLATED,
                                    private_dns_enabled=True)

    ########################################
    ##
    ## Code Artifact Domain and Repository Creation
    ##
    #########################################
    # Name for the pypi repo we create to mirror pypi.
    self.domain = None
    self.domain_name = 'enterprise-repo-domain'
    self.pypi_repo_name = "pypi-store"
    self.repo_name= "enterprise-repo"
    self.domain = codeartifact.CfnDomain(self, "cfndomain", domain_name=self.domain_name)
    
    self.pypi_repo = self.create_pypi_repo()
    self.code_repo = self.create_code_repo()

    # Specify the dependencies so the stack can be properly created.
    self.pypi_repo.add_depends_on(self.domain)
    self.code_repo.add_depends_on(self.pypi_repo)

    code_artifact_url = f"https://aws:{{}}@{self.domain_name}-{Aws.ACCOUNT_ID}.d.codeartifact.{Aws.REGION}.amazonaws.com/pypi/{self.repo_name}/simple/"

    ########################################
    ##
    ## Glue Connection
    ##
    #########################################
    self.sg_glue_conn = ec2.SecurityGroup(self, 
                                          id='sg_demo_glue_conn',
                                          vpc=self.vpc,
                                          allow_all_outbound=True,
                                          description='Security Group for Glue Connection')
    self.sg_glue_conn.add_ingress_rule(peer=self.sg_glue_conn,
                                       connection=ec2.Port.all_traffic())

    ####################################
    ##
    ## GLue Job Role Policy
    ##
    ####################################
    glue_job_role_iam_policy = iam.ManagedPolicy(self, 
                                                 "GlueJobIamPolicy",
                                                 managed_policy_name = 'enterprise-repo-glue-job-policy', 
                                                 description         = "Glue Job IAM Policy")
   
    glue_job_role_iam_policy.add_statements(iam.PolicyStatement(effect   =iam.Effect.ALLOW,
                                                                actions  =["s3:*"],
                                                                resources=[""+bucket.bucket_arn+"/*",
                                                                           ""+bucket.bucket_arn+""],))

    glue_job_role_iam_policy.add_statements(iam.PolicyStatement(effect   =iam.Effect.ALLOW,
                                                                actions  =["iam:PassRole"],
                                                                resources=['*'],
                                                                conditions={
                                                                  'StringLike': {
                                                                    "iam:PassedToService": ["glue.amazonaws.com"]
                                                                    }
                                                                  }))


    self.glue_job_role = iam.Role(self,
                                  id="glue_job_role",
                                  role_name="enterprise_repo_glue_job_role",
                                  assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
                                  path        = "/service-role/")
    self.glue_job_role.add_managed_policy(glue_job_role_iam_policy)
    self.glue_job_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole"))
    
    ########################################
    ##
    ## Glue Database
    ##
    #########################################

    glue_database = glue.Database(self,
                                  id='enterprise-repo-glue-db',
                                  database_name='codeartifactblog_glue_db')

    ########################################
    ##
    ## Glue Spark
    ##
    #########################################

    self.glue_conn = glue.Connection(self, id='enterprise_repo_glue_conn',
                                     type=glue.ConnectionType.NETWORK,
                                     connection_name='enterprise-repo-glue-connection',
                                     security_groups=[self.sg_glue_conn],
                                     subnet=self.vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED).subnets[0])

    glue_job = glue.Job(self, "enterprise_repo_spark_etl_job",
                        executable=glue.JobExecutable.python_etl(glue_version=glue.GlueVersion.V3_0,
                                                                 python_version=glue.PythonVersion.THREE,
                                                                 script=glue.Code.from_asset( "./scripts/glue/job.py")),
                        connections=[self.glue_conn],
                        role=self.glue_job_role,
                        worker_count = 3,
                        job_name = 'enterprise-repo-glue-job',
                        worker_type = glue.WorkerType.G_1_X,
                        continuous_logging=glue.ContinuousLoggingProps(enabled=True),
                        max_retries = 0,
                        enable_profiling_metrics = True,
                        timeout=Duration.minutes(20),
                        default_arguments={'--additional-python-modules': 'awswrangler',
                                           '--class': 'GlueApp',
                                           '--S3_BUCKET': ""+bucket.bucket_name+"",
                                           '--GLUE_DATABASE': ""+glue_database.database_name+"",
                                           '--python-modules-installer-option': ''},
                        description="an example Python ETL job")

    ####################################
    ##
    ## State Machine Execution Role Policy
    ##
    ####################################
    sfn_execution_role_iam_policy = iam.ManagedPolicy(self, 
                                                      "enterprise_repo_sfn_iam_policy",
                                                      managed_policy_name = 'enterprise-repo-sfn-policy',
                                                      description         = "SFN IAM Policy")

    sfn_execution_role_iam_policy.add_statements(iam.PolicyStatement(effect   =iam.Effect.ALLOW,
                                                                     actions  =["s3:PutObject",
                                                                                "s3:GetObject"],
                                                                     resources=[""+bucket.bucket_arn+"/*"]))

    ########################################
    ##
    ## State Machine
    ##
    #########################################
    with open('./scripts/statemachine/sfn.json') as f:
        json_definition = json.load(f)

    json_definition["States"]["GenerateCodeArtifactURL"]["Parameters"]["codeartifacturl.$"] = "States.Format('--index-url="+code_artifact_url.strip()+"', $.taskresult.AuthorizationToken)".strip()
    definition = json.dumps(json_definition, indent = 4)
    
    self.sfn_role = iam.Role(self,
                             id="sfn_role",
                             role_name="enterprise_repo_sfn_role",
                             assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
                             path        = "/service-role/")
    self.sfn_role.add_managed_policy(sfn_execution_role_iam_policy)
    self.sfn_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess"))
    self.sfn_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeArtifactReadOnlyAccess"))
    self.sfn_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole"))
    
    
    state_machine = sfn.CfnStateMachine(self,
                                        "enterprise_repo_state_machine",
                                        role_arn=self.sfn_role.role_arn,
                                        state_machine_name='enterprise-repo-step-function',
                                        definition_string=definition,
                                        definition_substitutions={"domain": self.domain_name,
                                                                  "aws_account_id": Aws.ACCOUNT_ID,
                                                                  "jobname": glue_job.job_name})

    ####################################
    ##
    ## Cfn Output
    ##
    ####################################

    CfnOutput(self, "Repository_Name",
      value       = self.repo_name,
      description = "Code Artifact Repository Name"
    )
    CfnOutput(self, "Domain_Name",
      value       = self.domain_name,
      description = "Code Artifact Domain name for Repository"
    )