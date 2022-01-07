import shlex
from redis import Redis

class NameSpacedRedis(Redis):
  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.max_batch = int(20)
    self.max_arguments = int(25)
    self.max_argument_size = int(256)
    self._get_commands()


  @staticmethod
  def _pairs_to_dict(response):
    if response is None:
        return {}
    it = iter(response)
    return dict(zip(it, it))


  @staticmethod
  def _key_spec_to_dict(response):
    ks = NameSpacedRedis._pairs_to_dict(response)
    ks['begin_search'] = NameSpacedRedis._pairs_to_dict(ks['begin_search'])
    ks['begin_search']['spec'] = NameSpacedRedis._pairs_to_dict(ks['begin_search']['spec'])
    ks['find_keys'] = NameSpacedRedis._pairs_to_dict(ks['find_keys'])
    ks['find_keys']['spec'] = NameSpacedRedis._pairs_to_dict(ks['find_keys']['spec'])
    return ks


  def _get_commands(self):
    conn = self.connection_pool.get_connection('COMMAND')
    conn.send_command('COMMAND')
    commands = conn.read_response()
    self.connection_pool.release(conn)
    self.commands = {}
    for command in commands:
      name = command[0]
      meta = self._pairs_to_dict(command[7])
      self.commands[name] = {
        'arity': command[1],
        'key_specs': [NameSpacedRedis._key_spec_to_dict(x) for x in meta.pop('key_specs', [])],
      }


  @staticmethod
  def _match_key_spec(arity, spec, argv):
    rep = []
    first, last, step = 0, 0, 0
    argc = len(argv)
    begin_type = spec['begin_search']['type']
    if begin_type == 'index':
      first = spec['begin_search']['spec']['index']
    elif begin_type == 'keyword':
      keyword = spec['begin_search']['spec']['keyword']
      start_from = spec['begin_search']['spec']['startfrom']
      start_index = start_from if start_from > 0 else argc + start_from
      end_index = argc - 1 if start_from > 0 else 0
      i = start_index
      incr = 1 if start_index <= end_index else -1
      while i != end_index:
        if i > argc:
          break
        if argv[i] == keyword:
          first = i + 1
          break
        i += incr
    else:
      return rep
    
    if first == 0:
      return rep
    
    find_type = spec['find_keys']['type']
    if find_type == 'range':
      step = spec['find_keys']['spec']['keystep']
      lastkey = spec['find_keys']['spec']['lastkey']
      limit = spec['find_keys']['spec']['limit']
      if lastkey >= 0:
        last = first + lastkey
      else:
        if limit != 0:
          last = first + (int((argc - first)/limit) + lastkey)
        else:
          last = argc + lastkey
    elif find_type == 'keynum':
      step = spec['find_keys']['spec']['keystep']
      firstkey = spec['find_keys']['spec']['firstkey']
      keynumidx = spec['find_keys']['spec']['keynumidx']
      keynum = argv[first + keynumidx]
      if not isinstance(keynumidx, int):
        return rep
      first += firstkey
      last = first + keynum - 1
    else:
      return rep

    for i in range(first, last + 1, step):
      if i >= argc:
        # Module and negative arity commands (TODO: find out if module command)
        if arity < 0:
          return []
        else:
          raise RuntimeError()  # Command key specs do not match arguments
      rep.append(i)
    return rep

  @staticmethod
  def _keys_index(argv, cmd):
    rep = []
    for spec in cmd['key_specs']:
      rep.extend(NameSpacedRedis._match_key_spec(cmd['arity'], spec, argv))
    return rep


  @staticmethod
  def _reply(value, error=False):
    return {
      'error': error,
      'value': value,
    }

  def _snip(self, value, init=0):
    ps = '... (full value snipped by the interwebz)'
    return value[:self.max_argument_size - init - len(ps)] + ps

  def execute(self, session, command):
    try:
      argv = shlex.split(command)
    except ValueError as e:
      return NameSpacedRedis._reply(str(e), True)
    argc = len(argv)
    if argc == 0:
      return NameSpacedRedis._reply(None, False)
    if argc > self.max_arguments:
      return NameSpacedRedis._reply(f'too many arguments - only up to {self.max_arguments} allowed on the interwebz', True)
    for i in range(argc):
      if type(argv[i]) is not str:
        return NameSpacedRedis._reply(f'expecting only strings but got {type(argv[i])} as argument', True)
      if len(argv[i]) > self.max_argument_size:
        argv[i] = self._snip(argv[i])
  
    # Locate the command in the SSOT
    cmd_name = argv[0].lower()
    is_subcmd = False
    if cmd_name not in self.commands:
      return NameSpacedRedis._reply(f'unknown command \'{argv[0]}\'', True)

    # Check if this is a subcommand
    if argc > 1:
        subcmd_name = f'{cmd_name} {argv[1].lower()}'
        is_subcmd = subcmd_name in self.commands
        if is_subcmd:
            cmd_name = subcmd_name

    # Pre-processing
    # TODO: potential "attack" vectors: append, bitfield, sadd, zadd, xadd, hset, lpush/lmove*, sunionstore, zunionstore, ...
    cmd = self.commands[cmd_name]
    if cmd_name == 'keys' and argc == 2:
      argv[1] = f'{session.id}:{argv[1]}'
    elif cmd_name == 'scan':
      match = False
      for i in range(argc-1):
        if argv[i].lower() == 'match':
          argv[i+1] = f'{session.id}:{argv[i+1]}'
          match = True
      if not match:
        argv.append('MATCH')
        argv.append(f'{session.id}:*')
        argc += 2
    # TODO: patterns may be extracted the from command arguments pecs, and if so
    # we can add support for `SORT` and potential future commands automatically
    elif cmd_name in ['flushdb', 'flushall']:
      session.relogin()  # Easier than finding them keys
      return NameSpacedRedis._reply('OK', False)
    elif cmd_name == 'setbit' and argc == 4:
      try:
        offset = int(argv[2])
        max_offset = self.max_argument_size * 8
        if offset > max_offset:
          return NameSpacedRedis._reply(f'offset too big - only up to {max_offset} bits allowed on the interwebz', True)
      except ValueError:
        pass  # let the server return a proper parsing error :)
    elif cmd_name == 'setrange' and argc == 4:
      try:
        offset = int(argv[2])
        argv[i] = self._snip(argv[i], init=offset)
      except ValueError:
        argv[i] = ''
    elif cmd_name in  ['quit', 'hello', 'reset', 'auth']: # TODO: ACL not applying?
      return NameSpacedRedis._reply('this command is not available on the interwebz', True)
    else:
      keys_index = self._keys_index(argv, cmd)
      for i in keys_index:
        argv[i] = f'{session.id}:{argv[i]}'

    # Send the command
    try:
      conn = self.connection_pool.get_connection(argv[0])
      conn.send_command(argv[0], *argv[1:])
      rep = conn.read_response()
    except Exception as e:
      return NameSpacedRedis._reply(str(e), True)
    finally:
      self.connection_pool.release(conn)

    # Post-processing
    if cmd_name == 'keys':
      rep = [x[len(str(session.id))+1:] for x in rep]
    elif cmd_name == 'scan':
      rep[1] = [x[len(str(session.id))+1:] for x in rep[1]]
    return NameSpacedRedis._reply(rep, False)


  def execute_commands(self, session, commands):
    if len(commands) > self.max_batch:
        return NameSpacedRedis._reply(f'batch too large - only up to {self.max_batch} commands allowed on the interwebz', True)
    return [self.execute(session, command) for command in commands]
