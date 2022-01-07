from flask import Flask, request, render_template
from flask_cors import CORS
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


  @app.route('/', methods=['GET'])
  def home():
    return render_template('home.html')

  @app.route('/', methods=['POST'])
  def post_command():
    handshake = bool(request.json['handshake']) # When true, a new session is always created
    commands = request.json['commands']         # A batch of commands for executions
    if type(commands) is not list:
      return "It posts commands as a list", 400
    ps = PageSession(handshake)
    # TODO: params creds
    conn = NameSpacedRedis.from_url('redis://interwebz:password1@localhost:6379', decode_responses=True)
    reply = {
      'reply': conn.execute_commands(ps, commands)
    }
    if debug_mode:
      reply.update({
        'id': ps.id,
        'commands': commands,
      })
    return reply


  return app
