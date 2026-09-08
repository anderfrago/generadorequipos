// Build-time extraction only. Production runs Python and has no JS server dependency.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = ['Schema.gs', 'ScoringService.gs', 'FunctionalService.gs', 'PersonalizationService.gs'].map(f => fs.readFileSync(path.join(root, f), 'utf8')).join('\n');
const data = vm.runInNewContext(source + `\nJSON.stringify({version:'V3_REDUCIDA', items:questionnaireItemSeed_(),conditions:conditionSeed_(),profiles:PROFILE_META,functional:FUNCTIONAL_META,personalization:PERSONALIZATION_TEXT})`);
fs.writeFileSync(path.join(root, 'backend/app/questionnaire.json'), JSON.stringify(JSON.parse(data), null, 2) + '\n');
