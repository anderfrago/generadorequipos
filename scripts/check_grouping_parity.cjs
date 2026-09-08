const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const fixtures = JSON.parse(fs.readFileSync(path.join(root,'tmp','grouping-fixtures.json'),'utf8'));
const source = ['AuthService.gs','Config.gs','ScoringService.gs','FunctionalService.gs','GroupingEngine.gs'].map(f=>fs.readFileSync(path.join(root,f),'utf8')).join('\n');
const context = vm.createContext({fixtures});
const results = vm.runInContext(source + `
fixtures.map(f=>{
 const x=f.model;
 const students=x.students.map(s=>({...s,studentId:s.id}));
 const model={students,byId:Object.fromEntries(students.map(s=>[s.studentId,s])),functionalCodes:x.functional_codes,functionalWeights:x.functional_weights,classFunctionalMean:x.means,classFunctionalQuantiles:Object.fromEntries(Object.entries(x.thresholds).map(([k,v])=>[k,{q35:v}])),classWeakShare:x.weak_share,relations:x.relations,config:{weights:x.weights,penaltyConcentration:16,penaltyDependency:18,penaltySevereImbalance:15,betterSeparatedPenalty:.22,togetherBonus:.1}};
 return GroupingEngine.evaluateProposal(model,f.teams,null);
})`,context);
fs.writeFileSync(path.join(root,'tmp','grouping-original.json'),JSON.stringify(results));
