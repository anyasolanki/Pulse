FROM flink:1.20.1-scala_2.12-java17
ADD https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar /opt/flink/lib/flink-sql-connector-kafka.jar
USER root
RUN chmod 644 /opt/flink/lib/flink-sql-connector-kafka.jar && mkdir -p /opt/flink/state && chown flink:flink /opt/flink/state
USER flink
