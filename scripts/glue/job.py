import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from awsglue.job import Job
import boto3
from glueutils import writer
import glueutils

## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'S3_BUCKET','GLUE_DATABASE'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

##Verify Versions of Imported Libraries
print("Boto3 Version    :   ",boto3.__version__)
print("Glue Utils Version :   " ,glueutils.__version__)

s3_input_path = 's3://' + args['S3_BUCKET'] + '/data/'
s3_output_path = 's3://' + args['S3_BUCKET'] + '/dataoutput/'
glue_db = args['GLUE_DATABASE']
glue_table = 'taxidataparquet'
partition_key_list=["year","app"]


sc = SparkContext.getOrCreate()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
dyf_input = glueContext.create_dynamic_frame.from_options("s3",  {"paths": [s3_input_path]}, 'csv',  {'withHeader': True} ,transformation_ctx = "DataSource0")
df_input = dyf_input.toDF()
df_input.createOrReplaceTempView("tempview_tbl")
df_output = spark.sql("select sum(trips) total_trips , week, year,app from tempview_tbl group by week, year, app")
dyf_output = DynamicFrame.fromDF(df_output, glueContext, "new_dynamic_frame")

writer.write_to_s3(glueContext,
                  dyf_output,
                   s3_output_path,
                   glue_table,
                   glue_db,
                   partition_key_list)
                   
print("Data written to S3. Glue Catalog Updated")

job.commit()
