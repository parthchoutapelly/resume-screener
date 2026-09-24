# SAM "makefile" build method for CommonLayer (docs/02-ingestion-pipeline.md §5.3).
# SAM invokes `make build-CommonLayer` with ARTIFACTS_DIR pointing at the
# staging directory it will zip into the layer version.
build-CommonLayer:
	mkdir -p "$(ARTIFACTS_DIR)/python" "$(ARTIFACTS_DIR)/data"
	cp -R layers/common_layer/python/rs_common "$(ARTIFACTS_DIR)/python/"
	cp data/*.json "$(ARTIFACTS_DIR)/data/"
