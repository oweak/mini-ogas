FROM golang:1.22-alpine AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/ ./cmd/
COPY internal/ ./internal/
RUN CGO_ENABLED=0 go build -o /out/node-agent ./cmd/node-agent

FROM alpine:3.20

COPY --from=build /out/node-agent /usr/local/bin/node-agent

CMD ["/usr/local/bin/node-agent"]
