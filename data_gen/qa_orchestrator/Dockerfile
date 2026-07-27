FROM python:3.13-slim

WORKDIR /app

COPY . /app

RUN pip install poetry
CMD poetry config repositories.azdo ${URL} && \
poetry version ${VERSION} && \
poetry build && \
poetry publish -r azdo --username ${USERNAME} --password ${PASSWORD}