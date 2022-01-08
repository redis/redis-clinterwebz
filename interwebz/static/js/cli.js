window.addEventListener('DOMContentLoaded', () => {
  var api_url = "http://localhost:5000/"; // TODO: API endpoint URL - parametrize
  var prompt_text = "redis:6379> "; // Prompt text
  var show_latency = 0.5;           // Show latency if execution exceeds this value (seconds)
  var show_debug = false;           // Show debug information after each request
  var history = [];                 // Command history
  var handshake = true;

  var cli = document.querySelector('.redis-cli'); // TODO: what about multiple cli elements?
  if (cli === null) return;

  var dbid = 'dbid' in cli.attributes ? cli.attributes['dbid'].value : '';
  var fullscreen = Boolean(cli.attributes['fullscreen']);
  var asciiart = Boolean(cli.attributes['asciiart']);

  var buffer = cli.firstElementChild;
  if (buffer === null) {
    buffer = document.createElement("pre");   // Lines buffer
    cli.appendChild(buffer);
  } else {
    history = buffer.textContent.split("\n").map(x => x.trim()).filter(x => x != '');
    buffer.textContent = '';
  }
  buffer.classList.add("buffer");

  // UI
  var prompt = document.createElement("div");   // Text prompt in input line
  prompt.classList.add("prompt");
  prompt.textContent = prompt_text;
  var input = document.createElement("input");  // User input
  input.classList.add("input");
  input.setAttribute("type", "text");
  input.setAttribute("autocomplete", "off");
  input.setAttribute("spellcheck", "false");
  var line = document.createElement("div");     // Prompt line
  line.classList.add("line");
  line.appendChild(prompt);
  line.appendChild(input);
  cli.appendChild(line);

  // Write to the buffer
  function write(text) {
    buffer.textContent += text;
  }

  // Write a line to the buffer
  function writeln(text) {
    write(`${text}\n`);
  }

  // Writes a reply from the API
  function format_resp2_reply(reply, indent='') {
    if (Array.isArray(reply)) {
      if (reply.length === 0) {
        // null array
        return '(empty array)\n'
      } else {
        let r = '';
        reply.forEach((x, i) => {
          if (i === 0) {
            r += (`${i+1}) `);
          } else {
            r += `${indent}${i+1}) `;
          }
          r += format_resp2_reply(x, indent + ' '.repeat((i+1).toString().length+2));
        });
        return r
      }
    } else if (reply === null) {
        return '(nil)\n'
    } else if (typeof (reply) === "string") {
      return `"${reply}"\n`
    } else if (typeof (reply) === "number") {
      return `(integer) ${reply}\n`;
    } else {
      return `-PROTOCOLERR Unknown reply type ${typeof(reply)}`;
    }
  }

  function add_reply(reply) {
    if (reply.error) {
      writeln(`(error) ${reply.value}`)
    } else {
      write(format_resp2_reply(reply.value));
    }
  }

  // Sends a command for API execution
  async function execute(commands) {
    if (commands.length === 0) {
      return [];
    }
    const response = await fetch(`${api_url}${dbid}`, {
      method: 'POST',
      mode: 'cors',
      cache: 'no-cache',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json'
      },
      // redirect: 'follow',
      // referrerPolicy: 'no-referrer', // no-referrer, *no-referrer-when-downgrade, origin, origin-when-cross-origin, same-origin, strict-origin, strict-origin-when-cross-origin, unsafe-url
      body: JSON.stringify({
        handshake,
        commands,
      }),   // body data type must match "Content-Type" header
    });
    handshake = false;
    if (response.status !== 200) {
      return {
        replies: [{
          value: `HTTP ${response.status}: ${response.statusText}`,
          error: true,
        }]
      }
    } else {
      return response.json(); // parses JSON response into native JavaScript objects
    }
  }

  // Run the user's command and print the reply
  function run_command(command) {
    const c = command.trim()
    let start = performance.now();
    prompt.hidden = true;

    execute([c])
      .then(data => {
        let time = (performance.now() - start) / 1000;
        if (data.replies !== undefined) {
          data.replies.forEach(reply => {
            add_reply(reply);
          });  
        } else {
          writeln('(error) server replied with nonsense');
        }
  
        if (c.length === 1 && show_latency !== 0 && time > show_latency) {
          writeln(`(${Number(time).toFixed(2)}s)`);
        }
        if (show_debug) {
          writeln(`DEBUG: ${JSON.stringify(data)}`);
        }  
      input.scrollIntoView();
        prompt.hidden = false;
      });
  }

  // Clicks, other than for selections, should focus on imput
  var capture = fullscreen ? document : cli;
  capture.addEventListener("click", () => {
    if (window.getSelection().toString() === '') input.focus();
  });
  // If a key is typed focus on the input
  capture.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) return;
    input.focus();
  }, false);

  // TODO: handle up/down arrows to browse history
  // TODO: handle autorepeat for printable characters
  input.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) return;
    const command = input.value;
    const c = command.trim().toLowerCase();
    if (e.key === 'Enter') {
      input.value = '';
      writeln(`${prompt_text}${command}`);
      switch (c) {
        case '':
          break;
        case 'clear':
          buffer.textContent = '';
          break;
        case 'history':
          history.forEach(x => writeln(x));
          break;
        case 'help':
          writeln(`No problem! Let me just open this url for you: https://redis.io/commands`);
          window.open('https://redis.io/commands');
          break;
        case '!debug':
          show_debug = true;
          writeln('DEBUG: on');
          break;
        default:
          run_command(command);
          history.push(command);
          break;
      }
      if (document.activeElement === input) input.scrollIntoView()
    } else if (e.key == 'ArrowUp') {
      // TODO: implement history browsing
    } else if (e.key == 'ArrowDown') {
      // TODO: implement history browsing
    }

  });

  if (asciiart) {
    time = new Date().toISOString()
    execute(['INFO SERVER'])
      .then(data => {
        if (data['replies'])
        raw = data['replies'][0]['value'];
        if (data['replies'][0]['error']) {
          buffer.textContent = `(error) ${raw}\n`;
          return
        }
        version = raw.match(/redis_version:(.*)/)[1];
        sha = raw.match(/redis_git_sha1:(.*)/)[1];
        dirty = raw.match(/redis_git_dirty:(.*)/)[1];
        bits = raw.match(/arch_bits:(.*)/)[1];
        port = raw.match(/tcp_port:(.*)/)[1]; 
        pid = raw.match(/process_id:(.*)/)[1];
        buffer.textContent = `${pid}:C ${time} # oO0OoO0OoO0Oo Redis is starting oO0OoO0OoO0Oo
${pid}:C ${time} # Configuration loaded
                 _._
            _.-\`\`__ ''-._
      _.-\`\`    \`.  \`_.  ''-._            Redis ${version} (${sha}/${dirty}) ${bits} bit
   .-\`\` .-\`\`\`.  \`\`\`\/    _.,_ ''-._
  (    '      ,       .-\`  | \`,    )     Running in standalone mode
  |\`-._\`-...-\` __...-.\`\`-._|'\` _.-'|     Port: ${port}
  |    \`-._   \`._    /     _.-'    |     PID: ${pid}
  \`-._    \`-._  \`-./  _.-'    _.-'
  |\`-._\`-._    \`-.__.-'    _.-'_.-'|
  |    \`-._\`-._        _.-'_.-'    |           https://redis.io
  \`-._    \`-._\`-.__.-'_.-'    _.-'
  |\`-._\`-._    \`-.__.-'    _.-'_.-'|
  |    \`-._\`-._        _.-'_.-'    |
  \`-._    \`-._\`-.__.-'_.-'    _.-'
      \`-._    \`-.__.-'    _.-'
          \`-._        _.-'
              \`-.__.-'

${pid}:M ${time} # Server initialized
${pid}:M ${time} * Ready to accept connections

${buffer.textContent}`;
      });
  }

  // Run to-be-historical commands
  if (history.length > 0) {
    execute(history)
    .then(data => {
      data.replies.forEach((reply, i) => {
        writeln(`${prompt_text}${history[i]}`);
        add_reply(reply);
      });  
    });
  }

  if (cli.attributes['fullscreen']) {
    input.focus();
  }
});
