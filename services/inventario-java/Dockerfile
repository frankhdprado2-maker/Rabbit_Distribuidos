FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -q -DskipTests dependency:go-offline
COPY src src
RUN mvn -q package
FROM eclipse-temurin:21.0.5_11-jre-alpine
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=build /src/target/inventario-1.0.0.jar app.jar
USER app
EXPOSE 8081
ENTRYPOINT ["java","-jar","/app/app.jar"]
