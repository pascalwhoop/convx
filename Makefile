.PHONY: build test

IMAGE := convx
PLATFORM ?= amd64

build:
	docker build --platform linux/$(PLATFORM) -t $(IMAGE):$(PLATFORM) .

test: build
	docker run --rm --entrypoint uv $(IMAGE):$(PLATFORM) run pytest -v
