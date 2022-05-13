
# Welcome to your Glue Code Artifact Python project!

Make sure the preqreuisites are completed
1. AWS CLI Installed
2. AWS CLI configured to an AWS account

Open the terminal/bash/shell

Browse to the current directory
```
$ cd <repo>/code/application/scripts/s3
``` 
Download the File from S3 bucket to current location:
```
$ aws s3 cp  s3://nyc-tlc/misc/FOIL_weekly_trips_apps.csv .
```
