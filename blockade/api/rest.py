#
#  Copyright (C) 2016 Dell, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from flask import Flask, abort, jsonify, request
from gevent.wsgi import WSGIServer

from blockade.api.manager import BlockadeManager
from blockade.config import BlockadeConfig
from blockade.errors import InvalidBlockadeName

import json
import os

app = Flask(__name__)


def start(data_dir='/tmp', port=5000, debug=False):
    BlockadeManager.set_data_dir(data_dir)
    app.debug = debug
    http_server = WSGIServer(('', port), app)
    http_server.serve_forever()


############## ERROR HANDLERS ##############


@app.errorhandler(415)
def unsupported_media_type(error):
    return 'Content-Type must be application/json', 415


@app.errorhandler(404)
def blockade_name_not_found(error):
    return 'Blockade name not found', 404


@app.errorhandler(InvalidBlockadeName)
def invalid_blockade_name(error):
    return 'Invalid blockade name', 400


################### ROUTES ###################


@app.route("/blockade")
def list_all():
    blockades = BlockadeManager.get_all_blockade_names()
    return jsonify(blockades=blockades)


@app.route("/blockade/<name>", methods=['POST'])
def create(name):
    if not request.headers['Content-Type'] == 'application/json':
        abort(415)

    if BlockadeManager.blockade_exists(name):
        return 'Blockade name already exists', 400

    # This will abort with a 400 if the JSON is bad
    data = request.get_json()
    config = BlockadeConfig.from_dict(data)
    BlockadeManager.store_config(name, config)

    b = BlockadeManager.get_blockade(name)
    containers = b.create()

    return '', 204


@app.route("/blockade/<name>/action", methods=['POST'])
def action(name):
    if not request.headers['Content-Type'] == 'application/json':
        abort(415)

    if not BlockadeManager.blockade_exists(name):
        abort(404)

    commands = ['start', 'stop', 'restart', 'kill']
    data = request.get_json()
    command = data.get('command')
    container_names = data.get('container_names')
    if command is None:
        return "'command' not found in body", 400
    if command not in commands:
        error_str = "'%s' is not a valid action" % command
        return error_str, 400
    if container_names is None:
        return "'container_names' not found in body", 400

    b = BlockadeManager.get_blockade(name)
    if 'kill' == command:
        signal = request.args.get('signal', 'SIGKILL')
        getattr(b, command)(container_names, signal=signal)
    else:
        getattr(b, command)(container_names)

    return '', 204


@app.route("/blockade/<name>/partitions", methods=['POST'])
def partitions(name):
    if not request.headers['Content-Type'] == 'application/json':
        abort(415)

    if not BlockadeManager.blockade_exists(name):
        abort(404)

    b = BlockadeManager.get_blockade(name)

    if request.args.get('random', False):
        b.random_partition()
        return '', 204

    data = request.get_json()
    partitions = data.get('partitions')
    if partitions is None:
        return "'partitions' not found in body", 400
    for partition in partitions:
        if not isinstance(partition, list):
            return "'partitions' must be a list of lists", 400

    b.partition(partitions)

    return '', 204


@app.route("/blockade/<name>/partitions", methods=['DELETE'])
def delete_partitions(name):
    if not BlockadeManager.blockade_exists(name):
        abort(404)

    b = BlockadeManager.get_blockade(name)
    b.join()

    return '', 204


@app.route("/blockade/<name>/network_state", methods=['POST'])
def network_state(name):
    if not request.headers['Content-Type'] == 'application/json':
        abort(415)

    if not BlockadeManager.blockade_exists(name):
        abort(404)

    network_states = ['flaky', 'slow', 'fast', 'duplicate']
    data = request.get_json()
    network_state = data.get('network_state')
    container_names = data.get('container_names')
    if network_state is None:
        return "'network_state' not found in body", 400
    if network_state not in network_states:
        error_str = "'%s' is not a valid network state" % network_state
        return error_str, 400
    if container_names is None:
        return "'container_names' not found in body", 400

    b = BlockadeManager.get_blockade(name)
    getattr(b, network_state)(container_names)

    return '', 204


@app.route("/blockade/<name>")
def status(name):
    if not BlockadeManager.blockade_exists(name):
        abort(404)

    containers = {}
    b = BlockadeManager.get_blockade(name)
    for container in b.status():
        containers[container.name] = container.to_dict()

    return jsonify(containers=containers)


@app.route("/blockade/<name>", methods=['DELETE'])
def destroy(name):
    if not BlockadeManager.blockade_exists(name):
        abort(404)

    b = BlockadeManager.get_blockade(name)
    b.destroy()

    BlockadeManager.delete_config(name)

    return '', 204
