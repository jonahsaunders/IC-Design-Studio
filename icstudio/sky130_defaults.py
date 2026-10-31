"""Source-backed starting dimensions for seven public short MOS symbols.

Only fresh instances are changed. Existing instance dimensions, catalog data,
model equations and saved PDK revisions are never rewritten. The ordinary
symbol for the same model supplies the reviewed valid starting dimensions.
"""
from pathlib import Path
from .model import digest,file_digest

FIELDS=('model','kind','prefix','pin_order','parameter_scale','parameters','emit_parameters')
CONTRACTS = {'sky130_fd_pr/nfet3_03v3_nvt.sym': {'model': 'sky130_fd_pr__nfet_03v3_nvt',
                                     'binding_sha256': 'c108580ca8a6243e6a1d8b0386c4791f9fb97bfb748fdca206b6bb62027dc49e',
                                     'initial_um': {'w': '1', 'l': '0.5'},
                                     'original_um': {'w': '1', 'l': '0.15'},
                                     'source_files': {'libs.tech/xschem/sky130_fd_pr/nfet3_03v3_nvt.sym': 'f61f5e571a328ef4aa18f84de25e11df388dcf815637e14246d14c8ef99f219e',
                                                      'libs.tech/xschem/sky130_fd_pr/nfet_03v3_nvt.sym': '7096f28bc53b3a052e34d828bf11d48d28b50745074842ebb1d4cf4635450471',
                                                      'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__nfet_03v3_nvt.pm3.spice': '042730a5b254b5508e4ef366784d972a8e10ed133f23ec7fdfc4ef9b3e545932'}},
 'sky130_fd_pr/nfet3_05v0_nvt.sym': {'model': 'sky130_fd_pr__nfet_05v0_nvt',
                                     'binding_sha256': 'b188f20864f91127cb3cfeee8aeddbfddf2be1a07768f13e240b56898354212f',
                                     'initial_um': {'w': '1', 'l': '0.9'},
                                     'original_um': {'w': '1', 'l': '0.15'},
                                     'source_files': {'libs.tech/xschem/sky130_fd_pr/nfet3_05v0_nvt.sym': 'a059deec8a913c61a76b6a7778411cf12c71dbd2a5232999e4ede11afcaf79d2',
                                                      'libs.tech/xschem/sky130_fd_pr/nfet_05v0_nvt.sym': 'bbd24024fbfcae20dec3995a1015c849421a65acba164a193c53c519de686d02',
                                                      'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__nfet_05v0_nvt.pm3.spice': 'c023cbfd9a518a3f9f87c45f85f7690324e23e5d1125bce37c84d2e3f9cc164c'}},
 'sky130_fd_pr/nfet3_g5v0d10v5.sym': {'model': 'sky130_fd_pr__nfet_g5v0d10v5',
                                      'binding_sha256': '2e552a3ac035880762e266f8e676b02ab65e5b9b71d43d58049af6fa5f6f5838',
                                      'initial_um': {'w': '1', 'l': '0.5'},
                                      'original_um': {'w': '1', 'l': '0.15'},
                                      'source_files': {'libs.tech/xschem/sky130_fd_pr/nfet3_g5v0d10v5.sym': '3c6d39ccd699535148423e16a1a209f3cd5ba2de420bdfca5559684a2a88b8c9',
                                                       'libs.tech/xschem/sky130_fd_pr/nfet_g5v0d10v5.sym': '63af67e853a09174db71fdaa685ff69fdb68552802222ffea0ac1f24680370aa',
                                                       'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__nfet_g5v0d10v5.pm3.spice': 'ea52c1dd85e6085994e7b6546b9b6616a3d8009f9b3294219c1018807f462257'}},
 'sky130_fd_pr/nfet3_g5v0d16v0.sym': {'model': 'sky130_fd_pr__nfet_g5v0d16v0',
                                      'binding_sha256': '56f0b53d3c89063e8fff7192c37e7614c81564aeba5aaaeff78b3771b4834b65',
                                      'initial_um': {'w': '5.0', 'l': '0.7'},
                                      'original_um': {'w': '1', 'l': '0.15'},
                                      'source_files': {'libs.tech/xschem/sky130_fd_pr/nfet3_g5v0d16v0.sym': 'b8f42b472250e8f79da6a8a91574f680930962df7d353b2e4d71d1889c93dd93',
                                                       'libs.tech/xschem/sky130_fd_pr/nfet_g5v0d16v0.sym': '2b142a521b3904d35da08b945398a3a189975518c17508b80d3fd417d17617ee',
                                                       'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__nfet_g5v0d16v0.pm3.spice': 'cc1977b2ce418e5a3df9a2e0ee328c0ea61c074d7489dbfa89206fca25c01169'}},
 'sky130_fd_pr/pfet3_01v8_lvt.sym': {'model': 'sky130_fd_pr__pfet_01v8_lvt',
                                     'binding_sha256': 'b292b7a37c7a2cf2b1429a698244366dd8c085c1c32ed9338df1f594b199b9f2',
                                     'initial_um': {'w': '1', 'l': '0.35'},
                                     'original_um': {'w': '1', 'l': '0.15'},
                                     'source_files': {'libs.tech/xschem/sky130_fd_pr/pfet3_01v8_lvt.sym': '612ea873e9ebee165e39ced707af6ae8fe16f266870b961875c16a9b19fd233b',
                                                      'libs.tech/xschem/sky130_fd_pr/pfet_01v8_lvt.sym': '926f35222e53f1c21ce149262fa2011975b9074fe58da505cad8f1eccf9605a8',
                                                      'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__pfet_01v8_lvt.pm3.spice': '26d67431c929be2c03cb1c31567251c5aa11107f14a7b7b5a945a5756b44d293'}},
 'sky130_fd_pr/pfet3_g5v0d10v5.sym': {'model': 'sky130_fd_pr__pfet_g5v0d10v5',
                                      'binding_sha256': '7952810429217cc2a4c03519ca6e484157f690ab4963f2e9589901f2c8698771',
                                      'initial_um': {'w': '1', 'l': '0.5'},
                                      'original_um': {'w': '1', 'l': '0.15'},
                                      'source_files': {'libs.tech/xschem/sky130_fd_pr/pfet3_g5v0d10v5.sym': '658de76e72c30270c6f3c617ea08dcdcff5e48d25bbfb15d206a442e6156b123',
                                                       'libs.tech/xschem/sky130_fd_pr/pfet_g5v0d10v5.sym': '68605e1a388175e9cbf74b72df6ea2fe2c100bb7bd4b8f333e7785be9d693739',
                                                       'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__pfet_g5v0d10v5.pm3.spice': '54798d6479ca546fb10a3e004e017e30e5cb46a70f53c37988e5705846e80f9a'}},
 'sky130_fd_pr/pfet3_g5v0d16v0.sym': {'model': 'sky130_fd_pr__pfet_g5v0d16v0',
                                      'binding_sha256': '742e25812f26141651dae1b68963906024bbe6f04077f25615d8a52d177676b8',
                                      'initial_um': {'w': '5.0', 'l': '0.66'},
                                      'original_um': {'w': '1', 'l': '0.15'},
                                      'source_files': {'libs.tech/xschem/sky130_fd_pr/pfet3_g5v0d16v0.sym': 'b47f61f094f2d93dd7e9d659f9a0529c9f23dd7699712424d9369ab8e55cd71e',
                                                       'libs.tech/xschem/sky130_fd_pr/pfet_g5v0d16v0.sym': 'd7c8a6b208717d5a7fcc9406c6e96ea9a91266d86d3937659a284d9fe5827c8e',
                                                       'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__pfet_g5v0d16v0.pm3.spice': 'e0bf3e15caf27abddd5980aba2d2f0152579307d5e966ed8c75a0fc9a82bfd8e'}}}

def initial_dimensions(technology,key,entry):
    lock=technology.get('package_lock',{})
    contract=CONTRACTS.get(key) if lock.get('id')=='sky130A' else None
    if not contract:return None
    # A user-customized binding or a different source revision retains its own
    # defaults; this reviewed correction must not guess at those semantics.
    if digest({k:entry.get(k) for k in FIELDS})!=contract['binding_sha256']:return None
    if any(lock.get('files',{}).get(name)!=expected for name,expected in contract['source_files'].items()):return None
    if not technology.get('package_root'):return None
    root=Path(technology['package_root']).resolve()
    for name,expected in contract['source_files'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=expected:
            raise ValueError('The source for this SKY130 starting geometry is missing or changed. Repair the PDK package.')
    return dict(contract['initial_um'])
