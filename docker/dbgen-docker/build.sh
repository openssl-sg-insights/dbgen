#!/usr/bin/env bash
#
#  Licensed to the Apache Software Foundation (ASF) under one   *
#  or more contributor license agreements.  See the NOTICE file *
#  distributed with this work for additional information        *
#  regarding copyright ownership.  The ASF licenses this file   *
#  to you under the Apache License, Version 2.0 (the            *
#  "License"); you may not use this file except in compliance   *
#  with the License.  You may obtain a copy of the License at   *
#                                                               *
#    http://www.apache.org/licenses/LICENSE-2.0                 *
#                                                               *
#  Unless required by applicable law or agreed to in writing,   *
#  software distributed under the License is distributed on an  *
#  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY       *
#  KIND, either express or implied.  See the License for the    *
#  specific language governing permissions and limitations      *
#  under the License.                                           *

IMAGE=${IMAGE:-dbgen}
TAG=${TAG:-latest}
DIRNAME=$(cd "$(dirname "$0")" && pwd)
DBGEN_ROOT="${DIRNAME}/../.."

set -e

echo "DBgen directory ${DBGEN_ROOT}"
echo "DBgen Docker directory ${DIRNAME}"

cd "${DBGEN_ROOT}"

echo "Copy distro ${DBGEN_ROOT}/dist/*.tar.gz ${DIRNAME}/dbgen.tar.gz"
cp ${DBGEN_ROOT}/dist/*.tar.gz "${DIRNAME}/dbgen.tar.gz"
cp ${DBGEN_ROOT}/requirements.txt "${DIRNAME}/requirements.txt"
cd "${DIRNAME}" && docker build --pull "${DIRNAME}" --tag="${IMAGE}:${TAG}" \
 --build-arg DEFAULT_ENV=/dbgen_files/default.py
rm "${DIRNAME}/dbgen.tar.gz"
rm "${DIRNAME}/requirements.txt"