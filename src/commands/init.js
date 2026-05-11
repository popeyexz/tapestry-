import { parseArgs } from 'node:util';
import { mkdirSync, writeFileSync, existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const AI_CONFIGS = {
  claude: {
    skillsDir: '.claude/skills',
    skillFile: 'uipro.md',
    templateFile: 'claude.md',
  },
};

export async function initCommand(args) {
  let values;
  try {
    ({ values } = parseArgs({
      args,
      options: {
        ai: { type: 'string' },
        global: { type: 'boolean', default: false },
      },
    }));
  } catch {
    console.error('Error: invalid arguments');
    printInitHelp();
    process.exit(1);
  }

  const { ai, global: isGlobal } = values;

  if (!ai) {
    console.error('Error: --ai flag is required\n');
    printInitHelp();
    process.exit(1);
  }

  const config = AI_CONFIGS[ai];
  if (!config) {
    console.error(`Error: unknown AI "${ai}". Supported: ${Object.keys(AI_CONFIGS).join(', ')}\n`);
    printInitHelp();
    process.exit(1);
  }

  const basePath = isGlobal ? homedir() : process.cwd();
  const skillsDir = join(basePath, config.skillsDir);
  const skillPath = join(skillsDir, config.skillFile);
  const templatePath = join(__dirname, '..', 'skills', config.templateFile);

  if (!existsSync(skillsDir)) {
    mkdirSync(skillsDir, { recursive: true });
  }

  const content = readFileSync(templatePath, 'utf8');
  writeFileSync(skillPath, content, 'utf8');

  console.log(`Installed uipro skill for ${ai}`);
  console.log(`  Location: ${skillPath}`);
}

function printInitHelp() {
  console.log('Usage: uipro init --ai claude [--global]\n');
  console.log('Options:');
  console.log('  --ai claude   AI assistant to install for');
  console.log('  --global      Install to home directory (~/.claude/skills/)');
}
