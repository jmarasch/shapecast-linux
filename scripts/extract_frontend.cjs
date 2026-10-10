// Recover a private test copy of embedded web assets from this purchased PE executable.
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto');
if(process.argv.length!==4){console.error('Usage: node extract_frontend.cjs <shapecast-shell.exe> <output-directory>');process.exit(2)}
const source=path.resolve(process.argv[2]),dest=path.resolve(process.argv[3]);
if(fs.existsSync(dest)&&fs.readdirSync(dest).length)throw Error('Output directory must be empty');
const bytes=fs.readFileSync(source);
if(bytes.length<64)throw Error('Truncated executable');
const pe=bytes.readUInt32LE(0x3c),coff=pe+4,opt=coff+20;
if(opt+32>bytes.length)throw Error('Truncated PE headers');
if(bytes.toString('ascii',pe,pe+4)!=='PE\0\0'||bytes.readUInt16LE(opt)!==0x20b)throw Error('Expected x64 PE');
const base=Number(bytes.readBigUInt64LE(opt+24)),sections=[];
if(!Number.isSafeInteger(base)||opt+bytes.readUInt16LE(coff+16)+40*bytes.readUInt16LE(coff+2)>bytes.length)throw Error('Invalid PE section table');
for(let i=0,off=opt+bytes.readUInt16LE(coff+16);i<bytes.readUInt16LE(coff+2);i++,off+=40)sections.push({name:bytes.toString('ascii',off,off+8).replace(/\0/g,''),rva:bytes.readUInt32LE(off+12),size:bytes.readUInt32LE(off+16),off:bytes.readUInt32LE(off+20)});
function fileOffset(va){for(const s of sections)if(va-base>=s.rva&&va-base<s.rva+s.size)return va-base-s.rva+s.off;return null}
const table=sections.find(s=>s.name==='.rdata'),found=new Map();
if(!table||table.off+table.size>bytes.length)throw Error('Invalid PE asset section');
for(let off=table.off;off+32<=table.off+table.size;off+=8){
 const pointer=Number(bytes.readBigUInt64LE(off)),len=Number(bytes.readBigUInt64LE(off+8));
 if(len<2||len>300)continue;const p=fileOffset(pointer);if(p===null||p+len>bytes.length)continue;
 const key=bytes.toString('utf8',p,p+len);if(!/^\/[a-zA-Z0-9_./@% -]+$/.test(key)||!(/\.(html|js|css|woff2?|png|svg|jpg|jpeg|webp|json|ico)$/.test(key)))continue;
 const dataOff=fileOffset(Number(bytes.readBigUInt64LE(off+16))),dataLen=Number(bytes.readBigUInt64LE(off+24));
 if(dataOff===null||dataLen<=0||dataLen>bytes.length||dataOff+dataLen>bytes.length)continue;
 let data;try{data=zlib.brotliDecompressSync(bytes.subarray(dataOff,dataOff+dataLen),{maxOutputLength:50*1024*1024})}catch{continue}
 if(key.split('/').includes('..'))throw Error('Unsafe asset path');
 if(found.has(key))continue;
 const target=path.resolve(dest,'.'+key);if(!target.startsWith(dest+path.sep))throw Error('Unsafe asset path');
 fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,data);
 found.set(key,{path:key,offset:dataOff,compressed_size:dataLen,size:data.length,sha256:crypto.createHash('sha256').update(data).digest('hex')});
}
if(!found.has('/index.html')||![...found.keys()].some(k=>k.endsWith('.js')))throw Error('No usable web interface was found');
fs.mkdirSync(dest,{recursive:true});fs.writeFileSync(path.join(dest,'extraction-manifest.json'),JSON.stringify({source,exe_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),assets:[...found.values()]},null,2));
console.log('Recovered',found.size,'assets');for(const a of found.values())if(/\.(html|js|css)$/.test(a.path))console.log(a.path,a.size);
