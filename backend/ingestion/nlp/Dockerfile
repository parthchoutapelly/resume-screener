# Container image, not zip+layers — D-56 (docs/Memory.md): the zip NlpLayer
# measured 310 MB unzipped for real (manylinux2014_x86_64) wheels, over
# Lambda's 250 MB function+layers combined limit. This was the pre-agreed
# fallback (D-03's own "revisit only if NLP exceeds 250 MB" condition).
#
# Unlike extraction, NLP has no native-binary dependency (no Tesseract), so
# it uses AWS's own Lambda base image directly via pip — no awslambdaric
# workaround needed, and it gets the Lambda Runtime Interface Emulator "for
# free" for local testing (sam local invoke).
#
# Docker context is ./backend (not this directory) so the image can COPY
# rs_common directly — container-image functions can't use layers.
FROM public.ecr.aws/lambda/python:3.12
COPY ingestion/nlp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}"
COPY layers/common_layer/python/rs_common ${LAMBDA_TASK_ROOT}/rs_common
# NOTE: backend/layers/common_layer/data/ is an empty placeholder — the real
# dictionaries live in backend/data/ and are only copied into THAT path by
# CommonLayer's makefile build (for zip-packaged functions using the layer).
# This image copies the real source directly instead.
COPY data ${LAMBDA_TASK_ROOT}/data
COPY ingestion/nlp/handler.py ${LAMBDA_TASK_ROOT}/
ENV RS_DATA_DIR=/var/task/data
CMD ["handler.lambda_handler"]
