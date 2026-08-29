# The adjudication sandbox.
#
# What runs in here is a patch written by an adversarial agent that was explicitly asked to make a
# test suite pass by any means. Importing it executes its module scope. On the host that is the
# largest gap this project has ever disclosed; in here it is a network-less, non-root, memory- and
# pid-capped container with the bundle mounted read-only.
#
# pytest is baked in rather than installed at run time on purpose: an image that has to `pip
# install` cannot be run with `--network none`, which is the whole point.
FROM python:3.12-slim

# Pinned. A floating pytest would make the adjudication's exit codes depend on when the image
# happened to be built, and those exit codes are the evidence every verdict cites.
RUN pip install --no-cache-dir pytest==8.3.4

# Never root, even inside a disposable container: a root process writing through a bind mount
# creates host files owned by root, and the bundle is mounted from the reviewer's checkout.
RUN useradd --create-home --uid 1000 runner
USER runner

# Bytecode would be the one thing the run tries to write back through a read-only mount.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0

WORKDIR /work
