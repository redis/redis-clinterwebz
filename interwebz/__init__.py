import sys
from typing import Any
from flask import Flask, request, render_template
from flask_cors import CORS
from .api import verify_commands, execute_commands
from .pagesession import PageSession
from .redis import NameSpacedRedis

def create_app(test_config=None):
  app = Flask(__name__, instance_relative_config=True)
  CORS(app, origins=[
    'http://localhost:1313',
    'http://127.0.0.1:1313',
    'https://redis.io',
    'https://try.redis.io'
  ])

  # TODO: Set the secret key to some random bytes. Keep this really secret!
  app.secret_key = b'interactiv3stuf!'
  debug_mode = True

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
  def home():
    return render_template('home.html')

  @app.route('/', methods=['POST'])
  def post_command():
    if 'handshake' in request.json:
      try:
        handshake = bool(request.json['handshake']) # When true, a new session is always created
      except ValueError:
        return 'Handshake must be a Boolean', 400
    if 'commands' in request.json:
      commands = request.json['commands']           # A batch of commands for executions
      unsane = verify_commands(commands)
      if unsane is not None:
        return unsane
    else:
      return ''

    psession = PageSession(handshake)
    # TODO: params creds
    client = NameSpacedRedis.from_url('redis://interwebz:password1@localhost:6379', decode_responses=True)
    reply = {
      'replies': execute_commands(client, psession , commands)
    }
    if debug_mode:
      reply.update({
        'id': psession.id,
        'commands': commands,
      })
    print(reply,file=sys.stderr)
    return reply

  return app
