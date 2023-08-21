FROM python:3-alpine

MAINTAINER Abner Palmeira <abnerpalmeira.dev>

RUN apk add --update && \
    pip install flask \
    && rm -rf /var/cache/apk/*

RUN mkdir /app

WORKDIR /app

EXPOSE 8000
