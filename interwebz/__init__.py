import json
import os
from typing import Any
from flask import Flask, request, render_template
from flask_cors import CORS
from . import default_settings
from .api import verify_commands, execute_commands
from .pagesession import PageSession
from .redis import NameSpacedRedis


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(default_settings)
    app.config.from_envvar('INTERWEBZ_SETTINGS', silent=True)
    json_settings = os.environ.get('INTERWEBZ_JSON_SETTINGS')
    if json_settings is not None:
        app.config.from_file(json_settings, load=json.load)
    CORS(app, **app.config['CORS'])

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # Set up database connections
    app.clients = {db['id']: NameSpacedRedis.from_url(
        db['url'], decode_responses=True) for db in app.config['DBS']}
    app.default_client = app.clients[app.config['DBS'][0]['id']]
    app.stack_client = app.clients['stack']

    def reply(value: Any, error: bool) -> dict:
        """ API reply object. """
        return {
            'value': value,
            'error': error,
        }

    @app.route('/', methods=['GET'])
    @app.route('/<dbid>', methods=['GET'])
    def home(dbid=None):
        return render_template('home.html', dbid=dbid)

    @app.route('/', methods=['POST'])
    @app.route('/<dbid>', methods=['POST'])
    def post_command(dbid=None):
        if 'commands' in request.json:
            commands = request.json['commands']
            insane = verify_commands(commands)
            if insane is not None:
                return insane
        else:
            return ''

        psession = PageSession()
        if commands[0].split(' ')[0].lower() in app.default_client.commands:
            client = app.default_client
        else:
            client = app.stack_client
        if dbid is not None:
            if dbid in app.clients:
                client = app.clients[dbid]
            else:
                return 'It must provide a valid dbid', 400

        reply = {
            'id': str(psession),
            'replies': execute_commands(client, psession, commands)
        }
        if app.config.get('INCLUDE_DEBUG_REPLY'):
            reply.update({
                'dbid': dbid,
                'commands': commands,
            })
        return reply

    return app
