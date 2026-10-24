"""Build the locked public ngspice release for the Linux/WSL model runtime.

Keep the complete original source archive, copying terms, build logs and binary
identity alongside the installed engine. The output directory must be new.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,tarfile,tempfile,urllib.request
from pathlib import Path

VERSION='47'
URL='https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/47/ngspice-47.tar.gz'
SOURCE_SHA256='894e649651f1838a14095e5a5439e7d3aa63e87ede14d283173fda4fcdef675f'
OPTIONS=['--with-x=no','--enable-osdi','--enable-xspice','--enable-klu','--enable-predictor','--disable-debug','CFLAGS=-O2']
CAPACITOR_SOURCE_SHA256='5ee51218fb36937ba55ee5e395ef837b34b65133914090db78d4930dae8f5e68'


def correct_capacitor_multiplier(source,retained):
    """Preserve m * 1e9 as an expression instead of concatenating exponents.

    eval_mvalue can return a scientific literal or a parameter expression.
    Appending 'e9' to either produces invalid syntax (e.g. 1.00000000e+00e9).
    Keep the original source and a unified patch beside the upstream archive.
    """
    import difflib
    path=Path(source)/'src/frontend/inpcom.c';original=path.read_bytes()
    if hashlib.sha256(original).hexdigest()!=CAPACITOR_SOURCE_SHA256:
        raise ValueError('Unexpected ngspice capacitor parser source.')
    old=b'ckt_array[0] = tprintf("g%s %s_int1 0 %s %s %se9", title_tok,'
    new=b'''for (char *mp = mstr; *mp; mp++) {
                    if (*mp == '{') *mp = '(';
                    else if (*mp == '}') *mp = ')';
                }
                ckt_array[0] = tprintf("g%s %s_int1 0 %s %s {(%s)*1e9}", title_tok,'''
    if original.count(old)!=1:raise ValueError('Unexpected capacitor multiplier expansion.')
    changed=original.replace(old,new);retained=Path(retained)
    (retained/'inpcom.c.original').write_bytes(original)
    patch=''.join(difflib.unified_diff(original.decode().splitlines(True),changed.decode().splitlines(True),
        fromfile='a/src/frontend/inpcom.c',tofile='b/src/frontend/inpcom.c'))
    (retained/'capacitor-multiplier.patch').write_bytes(patch.encode());path.write_bytes(changed)
    return dict(path='src/frontend/inpcom.c',original_sha256=CAPACITOR_SOURCE_SHA256,
                modified_sha256=sha(path),patch_sha256=sha(retained/'capacitor-multiplier.patch'))


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_archive(path):
    if sha(path)!=SOURCE_SHA256:raise ValueError('ngspice source archive differs from the locked public release.')


def relocate_initializer(output,build_prefix=None):
    """Prepare generated model paths and threads; retain the upstream initializer.

    ngspice expands an environment string as one argument (including spaces).
    Literal quote characters in a codemodel argument instead become part of its
    filename. The launcher controls both model and script directories locally.
    """
    output=Path(output).resolve();installed=output/'installed'
    initializer=installed/'share/ngspice/scripts/spinit'
    original=initializer.read_bytes();text=original.decode()
    if text.count('set num_threads=8')!=1:raise ValueError('Unexpected default ngspice thread setting.')
    # Small analog circuits are dominated by barriers with the upstream eight
    # threads. Users can still select a larger count in their control program.
    text=text.replace('set num_threads=8','set num_threads=1')
    prefix=str(Path(build_prefix or installed)/'lib/ngspice')+'/'
    names=[];lines=[]
    for line in text.splitlines(keepends=True):
        if line.strip().startswith(('codemodel ','osdi ')):
            match=re.fullmatch(r'(\s*)(codemodel|osdi) '+re.escape(prefix)+r'([A-Za-z0-9_.-]+)\s*',line)
            if not match:raise ValueError('Unexpected ngspice startup model declaration.')
            indent,command,name=match.groups()
            if command=='codemodel' and not (installed/'lib/ngspice'/name).is_file():
                raise ValueError('Missing installed ngspice code model: '+name)
            names.append((command,name));line=indent+command+' $ICSTUDIO_SPICE_MODELS/'+name+'\n'
        lines.append(line)
    if len([name for kind,name in names if kind=='codemodel'])!=7:
        raise ValueError('The locked ngspice release must install seven code models.')
    retained=output/'sources/spinit.original'
    if retained.exists():raise ValueError('The ngspice initializer has already been prepared.')
    retained.write_bytes(original);initializer.write_bytes(''.join(lines).encode())
    launcher=installed/'bin/icstudio-ngspice'
    launcher.write_bytes(b'''#!/bin/sh
set -eu
installed=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export SPICE_LIB_DIR="$installed/share/ngspice"
export SPICE_SCRIPTS="$SPICE_LIB_DIR/scripts"
export ICSTUDIO_SPICE_MODELS="$installed/lib/ngspice"
exec "$installed/bin/ngspice" "$@"
''');launcher.chmod(0o755)
    (output/'sources/ICSTUDIO-MODIFICATIONS.txt').write_text(
        'IC Design Studio changes generated spinit paths to the launcher-controlled '
        'ICSTUDIO_SPICE_MODELS directory and defaults to one simulation thread. Original initializer, complete unmodified source archive '
        'and upstream COPYING are retained. The source build also corrects nonlinear '
        'capacitor multiplier formatting from concatenated exponents to m*1e9; '
        'inpcom.c.original and capacitor-multiplier.patch retain that exact change. '
        'PDK model equations are unchanged.\n')
    return dict(original_sha256=sha(retained),initializer_sha256=sha(initializer),
        launcher='installed/bin/icstudio-ngspice',launcher_sha256=sha(launcher),
        code_models={name:sha(installed/'lib/ngspice'/name) for kind,name in names if kind=='codemodel'})


def build(output,archive=None,jobs=2):
    if sys.platform!='linux':raise ValueError('Build the included simulation runtime on Linux.')
    if not 1<=jobs<=16:raise ValueError('Choose between 1 and 16 build workers.')
    output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new ngspice runtime output directory.')
    if archive:verify_archive(archive)
    output.mkdir(parents=True);sources=output/'sources';sources.mkdir();logs=output/'build-logs';logs.mkdir()
    locked=sources/'ngspice-47.tar.gz'
    if archive:shutil.copyfile(archive,locked)
    else:
        with urllib.request.urlopen(URL,timeout=120) as response,locked.open('wb') as stream:shutil.copyfileobj(response,stream)
    verify_archive(locked)
    record=dict(schema=1,version=VERSION,source_url=URL,source_archive_sha256=SOURCE_SHA256,configure=OPTIONS,status='building')
    try:
        with tempfile.TemporaryDirectory(prefix='icstudio-ngspice-',dir=output.parent) as tmp:
            tmp=Path(tmp)
            with tarfile.open(locked) as source:source.extractall(tmp,filter='data')
            source=tmp/'ngspice-47';working=tmp/'build';working.mkdir()
            shutil.copyfile(source/'COPYING',sources/'COPYING')
            record['source_corrections']=[correct_capacitor_multiplier(source,sources)]
            commands=[[str(source/'configure'),'--prefix='+str(output/'installed'),*OPTIONS],['make','-j'+str(jobs)],['make','install']]
            for i,command in enumerate(commands):
                print('ngspice build stage',i+1,flush=True)
                with (logs/f'stage-{i}.log').open('w') as log:
                    subprocess.run(command,cwd=working,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
            config=(working/'config.log').read_text();shutil.copyfile(working/'config.log',logs/'config.log')
            features={name:bool(re.search(r'^#define '+name+r'(?:\s|$)',config,re.M)) for name in ('OSDI','XSPICE','KLU','PREDICTOR')}
            if not all(features.values()):raise ValueError('Required ngspice build features are absent: '+str(features))
        relocation=relocate_initializer(output)
        executable=output/'installed/bin/ngspice'
        version=subprocess.check_output([str(executable),'--version'],text=True)
        if not re.search(r'\bngspice-47\b',version):raise ValueError('The installed simulator reports another version.')
        (logs/'version.log').write_text(version)
        record.update(status='built',executable='installed/bin/ngspice',executable_sha256=sha(executable),features=features,relocation=relocation,
            copying_sha256=sha(sources/'COPYING'),scope='Build identity only; numerical, model and installed-runtime qualification are separate gates.')
    except BaseException as error:
        record.update(status='failed',error=repr(error));raise
    finally:(output/'source-lock.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--archive',type=Path);p.add_argument('--jobs',type=int,default=2);a=p.parse_args();print(json.dumps(build(a.output,a.archive,a.jobs),indent=2))
