ARG MAKE_PYTHON_VERSION
ARG DOCKER_BUILD_ENV
FROM python:${TRAVIS_PYTHON_VERSION:-3.11}-bookworm
# updated image names: https://hub.docker.com/_/python

WORKDIR /usr/src/app

ENV CURL_FLAGS="--proto =https --tlsv1.2 -sSf -L --max-redirs 1 -O"

ENV DEBIAN-FRONTEND noninteractive
ENV DISPLAY=:1

# install apt dependencies
RUN apt-get update && apt-get install -y xvfb firefox-esr libpq-dev python3-dev && \
    apt-get install -y libsqlite3-0 ca-certificates gnupg && apt-get clean

# install node (updated to v20) https://github.com/nodesource/distributions#debian-versions
RUN mkdir -p /etc/apt/keyrings
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
ENV NODE_MAJOR=20
RUN echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list
RUN apt-get install -y nodejs

# install geckodriver
ENV GECKODRIVER_VERSION="v0.33.0"
ENV GECKODRIVER_SHA=5f5e89bb31fe5f55f963f56ef7e55a5c8e9dc415d94b1ddc539171a327b8e6c4
ENV GECKODRIVER_BASE_URL="https://github.com/mozilla/geckodriver/releases/download"
RUN curl ${CURL_FLAGS} \
      ${GECKODRIVER_BASE_URL}/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-linux64.tar.gz
RUN echo "${GECKODRIVER_SHA}  geckodriver-${GECKODRIVER_VERSION}-linux64.tar.gz" | sha256sum --check -
RUN mkdir geckodriver
RUN tar -xzf geckodriver-${GECKODRIVER_VERSION}-linux64.tar.gz -C geckodriver

# install yarn
RUN curl -sL https://dl.yarnpkg.com/debian/pubkey.gpg | gpg --dearmor | tee /usr/share/keyrings/yarnkey.gpg >/dev/null
RUN echo "deb [signed-by=/usr/share/keyrings/yarnkey.gpg] https://dl.yarnpkg.com/debian stable main" | tee /etc/apt/sources.list.d/yarn.list
RUN apt-get update && apt-get install yarn
RUN mkdir /var/www ./node_modules /.cache /.yarn /.mozilla
RUN touch /usr/src/app/yarn-error.log
COPY yarn.lock /usr/src/app/
RUN chmod -R 777 /usr/src/app/ /var/lib/xkb /.cache /.yarn /.mozilla


COPY requirements.txt dev-requirements.txt /usr/src/app/
RUN pip3 install --no-cache-dir -r requirements.txt

RUN test "${DOCKER_BUILD_ENV}" = production || pip3 install --no-cache-dir -r dev-requirements.txt

COPY package.json /usr/src/app/
RUN yarn

COPY test_data.py /usr/src/app/
COPY mypy.ini /usr/src/app/
EXPOSE 3000

ENV PATH="/usr/src/app/geckodriver:${PATH}"
ENV SECRET_KEY 4Q6ZaQQdiqtmvZaxP1If
ENV SQLALCHEMY_DATABASE_URI postgresql://openoversight:terriblepassword@postgres/openoversight-dev

WORKDIR /usr/src/app/

CMD ["OpenOversight/scripts/entrypoint_dev.sh"]
