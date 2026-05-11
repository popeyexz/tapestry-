import { initCommand } from './commands/init.js';

const [, , command, ...args] = process.argv;

const COMMANDS = {
  init: initCommand,
};

function printHelp() {
  console.log('uipro - connect apps from every platform and terminal CLI in one\n');
  console.log('Usage: uipro <command> [options]\n');
  console.log('Commands:');
  console.log('  init    Install a uipro skill into an AI assistant\n');
  console.log('Examples:');
  console.log('  uipro init --ai claude --global   # Install to ~/.claude/skills/');
}

if (!command || command === '--help' || command === '-h') {
  printHelp();
  process.exit(0);
}

if (!COMMANDS[command]) {
  console.error(`Unknown command: ${command}`);
  printHelp();
  process.exit(1);
}

await COMMANDS[command](args);
