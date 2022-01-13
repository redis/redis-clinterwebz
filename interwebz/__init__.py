import json
import os
import sys
from typing import Any
from flask import Flask, request, render_template
from flask_cors import CORS
from . import default_settings
from .api import verify_commands, execute_commands
from .pagesession import PageSession
from .redis import NameSpacedRedis, exceptions

def create_app(test_config=None):
  app = Flask(__name__, instance_relative_config=True)
  app.config.from_object(default_settings)
  app.config.from_envvar('INTERWEBZ_SETTINGS', silent=True)
  json_settings = os.environ.get('INTERWEBZ_JSON_SETTINGS')
  if json_settings is not None:
    print(json_settings, file=sys.stderr)
    app.config.from_file(json_settings, load=json.load)
    pass
  CORS(app, **app.config['CORS'])

  if test_config is None:
      # load the instance config, if it exists, when not testing
      app.config.from_pyfile('config.py', silent=True)
  else:
      # load the test config if passed in
      app.config.from_mapping(test_config)

  def reply(value:Any, error:bool) -> dict:
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
  def post_command(dbid = None):
    if 'commands' in request.json:
      commands = request.json['commands']           # A batch of commands for executions
      unsane = verify_commands(commands)
      if unsane is not None:
        return unsane
    else:
      return ''

    psession = PageSession()
    dburl = None
    if dbid is None:
      dburl = app.config['DBS'][0]['url']
    else:
      for db in app.config['DBS']:
        if db['id'] == dbid:
          dburl = db['url']
          break
    if dburl is None:
      return 'It must provide a valid dbid', 400

    reply = {
      'id': psession.id,
      'replies': execute_commands(dburl, psession, commands)
    }
    if app.config.get('INCLUDE_DEBUG_REPLY'):
      reply.update({
        'dbid': dbid,
        'commands': commands,
      })
    return reply

  return app
