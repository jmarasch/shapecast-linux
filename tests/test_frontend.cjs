// Synthetic PE/Brotli fixture: no Shapecast code or assets required.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),zlib=require('node:zlib'),cp=require('node:child_process'),assert=require('node:assert/strict');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'frontend-fixture-'));
function fixture(keys){
 const bytes=Buffer.alloc(8192),pe=0x80,coff=pe+4,opt=coff+20,section=opt+0xf0,base=0x140000000;
 bytes.writeUInt32LE(pe,0x3c);bytes.write('PE\0\0',pe,'ascii');bytes.writeUInt16LE(1,coff+2);bytes.writeUInt16LE(0xf0,coff+16);bytes.writeUInt16LE(0x20b,opt);bytes.writeBigUInt64LE(BigInt(base),opt+24);
 bytes.write('.rdata',section);bytes.writeUInt32LE(0x1000,section+12);bytes.writeUInt32LE(0x1c00,section+16);bytes.writeUInt32LE(0x400,section+20);
 let data=0x800;
 keys.forEach((key,i)=>{const content=Buffer.from(key.endsWith('.html')?'<title>Fixture</title>':'console.log("fixture");'),compressed=zlib.brotliCompressSync(content),name=Buffer.from(key),record=0x400+i*32;
 bytes.writeBigUInt64LE(BigInt(base+0x1000+data-0x400),record);bytes.writeBigUInt64LE(BigInt(name.length),record+8);name.copy(bytes,data);data+=name.length;
 bytes.writeBigUInt64LE(BigInt(base+0x1000+data-0x400),record+16);bytes.writeBigUInt64LE(BigInt(compressed.length),record+24);compressed.copy(bytes,data);data+=compressed.length;
 });return bytes;
}
function run(bytes,name){const file=path.join(root,name+'.exe'),output=path.join(root,name);fs.writeFileSync(file,bytes);return {result:cp.spawnSync(process.execPath,[path.join(__dirname,'../scripts/extract_frontend.cjs'),file,output],{encoding:'utf8'}),output};}
try{
 const good=run(fixture(['/index.html','/assets/app.js']),'good');assert.equal(good.result.status,0,good.result.stderr);assert.equal(JSON.parse(fs.readFileSync(path.join(good.output,'extraction-manifest.json'))).assets.length,2);
 const bad=run(fixture(['/index.html','/../escape.js']),'bad');assert.notEqual(bad.result.status,0);assert.equal(fs.existsSync(path.join(root,'escape.js')),false);
 assert.notEqual(run(Buffer.alloc(10),'truncated').result.status,0);
 console.log('Synthetic frontend extraction tests passed.');
}finally{fs.rmSync(root,{recursive:true,force:true});}
