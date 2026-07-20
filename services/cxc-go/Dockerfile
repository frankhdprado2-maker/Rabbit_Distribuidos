FROM golang:1.22.11-alpine AS build
WORKDIR /src
COPY go.mod go.sum* ./
COPY . .
RUN go mod tidy && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /cxc ./cmd/cxc
FROM alpine:3.21.2
RUN addgroup -S app && adduser -S app -G app
COPY --from=build /cxc /usr/local/bin/cxc
USER app
EXPOSE 8084
ENTRYPOINT ["cxc"]
