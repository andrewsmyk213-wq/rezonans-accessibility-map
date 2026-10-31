const fs=require('fs'), vm=require('vm'), assert=require('assert');
let script=fs.readFileSync('app.js','utf8').replace('init();\n})();','globalThis.testAPI={parseGeoJSON,statusFor,suitability,filtered,state,demoPath,category,photoReference};\n})();');
const context={localStorage:{getItem:()=>null},URL,console}; vm.createContext(context); vm.runInContext(script,context);
const {parseGeoJSON,statusFor,suitability,filtered,state,demoPath,category,photoReference}=context.testAPI;
const point=(id,name,props={})=>({type:'Feature',geometry:{type:'Point',coordinates:[25.94,48.29]},properties:{name,source_record_id:id,source_id:'openstreetmap',...props}});
const places=parseGeoJSON({type:'FeatureCollection',features:[point('node/1','Лікарня',{wheelchair:'yes',address:'Головна 1',category:'hospital'}),point('node/2','Аптека',{wheelchair:'no',category:'pharmacy'}),point('node/3','Музей',{}),point('node/4','Конфлікт',{wheelchair:'yes',ramp:'no'})]}).places;
assert.equal(places.length,4); assert.equal(parseGeoJSON({type:'FeatureCollection',features:[]}).places.length,0);
assert.equal(statusFor(places[0]).key,'good'); assert.equal(statusFor(places[1]).key,'bad'); assert.equal(statusFor(places[2]).key,'unknown'); assert.equal(statusFor(places[3]).key,'good');
state.current=places; state.search='головна'; assert.equal(filtered().length,1); assert.equal(statusFor(filtered()[0]).key,'good');
state.search='';state.cat='health'; assert.equal(filtered().length,2);state.cat='all';state.accessFilter='unknown';assert.equal(filtered().length,1);
state.accessFilter='all';state.needs.entrance=true;assert.equal(statusFor(filtered()[0]).key,'good');
assert(suitability(places[1]).problem.includes('вхід'));state.needs.entrance=false;assert(!suitability(places[1]).problem.includes('вхід'));
assert(demoPath(false).path.includes('Сходи'));assert(demoPath(true).path.includes('Обхід'));
console.log('PASS: GeoJSON, empty dataset, source statuses, name/address search, categories, accessibility filtering and sorting');

const mappings=[['restaurant','restaurant'],['cafe','cafe'],['fast_food','fast_food'],['bank','bank'],['atm','bank'],['toilets','toilets'],['cinema','culture'],['school','education'],['townhall','public']];for(const [tag,want] of mappings)assert.equal(category({raw_properties:{amenity:tag}}),want);
assert.equal(category({raw_properties:{shop:'supermarket'}}),'supermarket');assert.equal(category({raw_properties:{shop:'books'}}),'retail');assert.equal(category({raw_properties:{tourism:'hotel'}}),'hotel');assert.equal(category({raw_properties:{tourism:'museum'}}),'culture');assert.equal(category({raw_properties:{leisure:'park'}}),'park');assert.equal(category({raw_properties:{public_transport:'platform'}}),'transport');
const food=parseGeoJSON({type:'FeatureCollection',features:[point('node/5','Cafe',{raw_properties:{amenity:'cafe'}}),point('node/6','Restaurant',{raw_properties:{amenity:'restaurant'}})]}).places;state.current=food;state.cat='food';state.search='cafe';assert.equal(filtered().length,1);assert.equal(statusFor(food[0]).key,'unknown');
assert.equal(photoReference({raw:{raw_properties:{wikimedia_commons:'File:Real.jpg'}}}).file,'File:Real.jpg');assert.equal(photoReference({raw:{raw_properties:{image:'https://evil.example/File:Real.jpg'}}}).file,'');assert.equal(photoReference({raw:{raw_properties:{wikidata:'Q123'}}}).wikidata,'Q123');assert.equal(photoReference({raw:{raw_properties:{wikidata:'Q1/../../bad'}}}).wikidata,'');
console.log('PASS: city category mapping, combined search/filter, unknown status and safe photo references');

const cases=[ [{wheelchair:'yes',ramp:'no'},'good'],[{ramp:'yes'},'unknown'],[{},'unknown'],[{stairs:'yes'},'bad'],[{wheelchair:'yes',raw_properties:{wheelchair:'no'}},'conflict'] ];for(const [props,want] of cases){const p=parseGeoJSON({type:'FeatureCollection',features:[point('case','Case',props)]}).places[0];assert.equal(statusFor(p).key,want)}
const osmFlat=parseGeoJSON({type:'FeatureCollection',features:[{type:'Feature',id:'node/444',geometry:{type:'Point',coordinates:[25.94,48.29]},properties:{name:'Flat',shop:'supermarket','addr:street':'Головна'}}]}).places[0];assert.equal(osmFlat.id,'openstreetmap:node/444');assert.equal(osmFlat.category,'supermarket');assert.equal(osmFlat.address,'Головна');console.log('PASS safety and standard GeoJSON regression');

const internals=fs.readFileSync('app.js','utf8').replace('init();\n})();','globalThis.details={detailItem};\n})();');vm.runInContext(internals,context);assert(context.details.detailItem('Сходи','yes','info','').includes('tag bad'));assert(context.details.detailItem('Сходи','no','info','').includes('tag good'));assert(!context.details.detailItem('Пандус','yes','info','').includes('tag good'));console.log('PASS attribute-specific indicators');
