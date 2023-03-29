from pyspark.sql import SparkSession
from pyspark.sql.types import *
from pyspark.sql.functions import *

BOOTSTRAP_SERVERS = "b-2.finalmskcluster.0lcx26.c13.kafka.us-east-1.amazonaws.com:9092,\
    b-3.finalmskcluster.0lcx26.c13.kafka.us-east-1.amazonaws.com:9092,\
    b-1.finalmskcluster.0lcx26.c13.kafka.us-east-1.amazonaws.com:9092"

if __name__ == "__main__":
    spark = SparkSession.builder.getOrCreate()
    schema = spark.read.json('s3://wcd-final-benimmerman/schema/final_schema.json').schema

    df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", BOOTSTRAP_SERVERS) \
        .option("subscribe", "dbserver1.final.flights") \
        .option("startingOffsets", "latest") \
        .load()

    transform_df = df.select(col("value").cast("string")).alias("value")\
        .withColumn("jsonData",from_json(col("value"),schema)).select("jsonData.payload.after.*")

    checkpoint_location = "s3://wcd-final-benimmerman/final_checkpoint/"

    table_name = 'flights'
    hudi_options = {
        'hoodie.table.name': table_name,
        "hoodie.datasource.write.table.type": "COPY_ON_WRITE",
        'hoodie.datasource.write.recordkey.field': 'icao24',
        'hoodie.datasource.write.partitionpath.field': 'icao24',
        'hoodie.datasource.write.table.name': table_name,
        'hoodie.datasource.write.operation': 'upsert',
        'hoodie.datasource.write.precombine.field': 'time_position',
        'hoodie.datasource.hive_sync.enable': True,
        'hoodie.datasource.hive_sync.database': 'final',
        'hoodie.datasource.hive_sync.table': 'flights',
        'hoodie.upsert.shuffle.parallelism': 100,
        'hoodie.insert.shuffle.parallelism': 100
    }

    s3_path = "s3://wcd-final-benimmerman/pyspark_output/flights/"


    def write_batch(batch_df, batch_id):
        batch_df.write.format("org.apache.hudi") \
        .options(**hudi_options) \
        .mode("append") \
        .save(s3_path)

    transform_df.writeStream.option("checkpointLocation", checkpoint_location) \
        .queryName("wcd-flights-streaming-app") \
        .foreachBatch(write_batch) \
        .start() \
        .awaitTermination()