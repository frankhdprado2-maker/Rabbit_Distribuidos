FROM mcr.microsoft.com/dotnet/sdk:8.0.404 AS build
WORKDIR /src
COPY src/Facturacion.Worker/Facturacion.Worker.csproj src/Facturacion.Worker/
RUN dotnet restore src/Facturacion.Worker/Facturacion.Worker.csproj
COPY src src
RUN dotnet publish src/Facturacion.Worker/Facturacion.Worker.csproj -c Release -o /out --no-restore
FROM mcr.microsoft.com/dotnet/runtime:8.0.11
WORKDIR /app
COPY --from=build /out .
USER app
ENTRYPOINT ["dotnet","Facturacion.Worker.dll"]
