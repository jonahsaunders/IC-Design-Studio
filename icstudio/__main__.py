import sys

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        from .worker import main as worker
        return worker(sys.argv[2],sys.argv[3])
    if len(sys.argv)>1 and sys.argv[1]=='--cli':
        from .cli import main as cli
        return cli(sys.argv[2:])
    if '--release-test' in sys.argv:
        from .release_probe import main as probe
        return probe(sys.argv[sys.argv.index('--release-test')+1])
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from .gui import Studio
    app=QApplication(sys.argv);app.setApplicationName('IC Design Studio');app.setOrganizationName('ICDesignStudio');app.setStyle('Fusion');window=Studio(recover='--smoke-test' not in sys.argv)
    if '--project' in sys.argv:
        from .model import load_project
        path=sys.argv[sys.argv.index('--project')+1];window.set_project(load_project(path),path)
    from PySide6.QtGui import QIcon
    from pathlib import Path
    app.setWindowIcon(QIcon(str(Path(__file__).parent/'assets/app.svg')))
    window.setWindowIcon(app.windowIcon())
    window.show()
    if '--smoke-test' in sys.argv:
        from .model import digest
        window.saved_hash=digest(window.project)
        QTimer.singleShot(600,app.quit)
    return app.exec()
if __name__=='__main__':raise SystemExit(main())
