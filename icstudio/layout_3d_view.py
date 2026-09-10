"""Interactive mesh rendering with a depth-buffered OpenGL desktop path."""
from array import array
import math

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QMatrix4x4, QPainter, QPen, QPolygonF,
                          QVector3D, QOpenGLContext, QOffscreenSurface, QSurfaceFormat)
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget

BACKGROUND = QColor('#101b2c')


class Camera:
    """Shared orthographic camera and interactions for both renderers."""
    def setup_camera(self):
        self.mesh = None
        self.yaw, self.pitch = -35., 55.
        self.zoom, self.z_scale, self.explode = 1., 1., 0.
        self.pan = QPointF()
        self.radius, self.center_z = 1., 0.
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 280)
        self.setAccessibleName('3D layout canvas')
        self.setToolTip('Drag to orbit; Shift-drag or right-drag to pan; scroll to zoom. F fits, 1 is isometric, 2 top, 3 front.')

    def set_mesh(self, mesh):
        self.mesh = mesh
        self.dirty = True
        self.fit()

    def layer_z(self, index, layer):
        return ((layer.z_um + index * self.explode) * self.z_scale,
                layer.thickness_um * self.z_scale)

    def fit(self):
        self.zoom, self.pan = 1., QPointF()
        if self.mesh:
            bounds = self.mesh.bounds_um
            heights = [(z, z + thickness) for i, layer in enumerate(self.mesh.layers)
                       if layer.visible and layer.triangles for z, thickness in [self.layer_z(i, layer)]]
            low = min((z[0] for z in heights), default=0.)
            high = max((z[1] for z in heights), default=1.)
            self.center_z = (low + high) / 2
            self.center_xy = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
            self.radius = max(.1, math.sqrt((bounds[2] - bounds[0]) ** 2 +
                              (bounds[3] - bounds[1]) ** 2 + (high - low) ** 2) / 2) * 1.12
        self.update()

    def preset(self, name):
        self.yaw, self.pitch = {'Isometric': (-35., 55.), 'Top': (0., 0.), 'Front': (0., 90.)}[name]
        self.update()

    def rotation(self):
        matrix = QMatrix4x4()
        matrix.rotate(-self.pitch, 1, 0, 0)
        matrix.rotate(self.yaw, 0, 0, 1)
        return matrix

    def matrix(self):
        r = self.radius / self.zoom
        aspect = max(1, self.width()) / max(1, self.height())
        rx, ry = r * max(1, aspect), r * max(1, 1 / aspect)
        matrix = QMatrix4x4()
        matrix.ortho(-rx, rx, -ry, ry, -self.radius * 20, self.radius * 20)
        matrix.translate(self.pan.x() * 2 * rx / max(1, self.width()),
                         -self.pan.y() * 2 * ry / max(1, self.height()), 0)
        matrix *= self.rotation()
        cx, cy = getattr(self, 'center_xy', (0, 0))
        matrix.translate(-cx, -cy, -self.center_z)
        return matrix

    def mousePressEvent(self, event):
        self.last_pos = event.position()
        self.setFocus()
        event.accept()

    def mouseMoveEvent(self, event):
        if not event.buttons() or not hasattr(self, 'last_pos'):
            return
        delta = event.position() - self.last_pos
        self.last_pos = event.position()
        if event.buttons() & (Qt.RightButton | Qt.MiddleButton) or event.modifiers() & Qt.ShiftModifier:
            self.pan += delta
        elif event.buttons() & Qt.LeftButton:
            self.yaw = (self.yaw + delta.x() * .5) % 360
            self.pitch = max(0., min(180., self.pitch + delta.y() * .5))
        self.update()

    def wheelEvent(self, event):
        self.zoom = max(.05, min(100., self.zoom * 1.15 ** (event.angleDelta().y() / 120)))
        self.update()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.fit()
        elif event.key() in (Qt.Key_1, Qt.Key_2, Qt.Key_3):
            self.preset({Qt.Key_1: 'Isometric', Qt.Key_2: 'Top', Qt.Key_3: 'Front'}[event.key()])
        else:
            super().keyPressEvent(event)

    def hud(self, painter):
        painter.setPen(QColor('#c6d5e8'))
        painter.drawText(18, 27, '3D LAYOUT  /  ' + ('CROPPED REGION' if self.mesh and self.mesh.cropped else 'ACTIVE CELL'))
        if not self.mesh or not self.mesh.triangle_count:
            painter.drawText(self.rect(), Qt.AlignCenter, 'No layout geometry in this region')
        elif not any(layer.visible and layer.triangles for layer in self.mesh.layers):
            painter.drawText(self.rect(), Qt.AlignCenter, 'All populated layers are hidden')
        center = QPointF(48, self.height() - 48)
        rotation = self.rotation()
        for label, vector, color in [('X', QVector3D(1, 0, 0), '#fa8b8b'),
                                     ('Y', QVector3D(0, 1, 0), '#7cd7a9'),
                                     ('Z', QVector3D(0, 0, 1), '#85baff')]:
            v = rotation.mapVector(vector)
            end = center + QPointF(v.x() * 27, -v.y() * 27)
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(center, end)
            painter.drawText(end + QPointF(4, -4), label)
        painter.setPen(QColor('#8fa4be'))
        painter.drawText(100, self.height() - 22, 'Drag: orbit   Shift / right drag: pan   Scroll: zoom   F: fit')


def shade(color, normal):
    light = max(0, sum(a * b for a, b in zip(normal, (.3, -.4, .8660254))))
    factor = .48 + .52 * light
    return QColor.fromRgbF(color.redF() * factor, color.greenF() * factor, color.blueF() * factor)


class SoftwareView(Camera, QWidget):
    """Portable painter fallback; intersecting solids can have ordering artifacts."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_camera()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND)
        if self.mesh:
            matrix, rotation, faces = self.matrix(), self.rotation(), []
            for i, layer in enumerate(self.mesh.layers):
                if not layer.visible:
                    continue
                z, thickness = self.layer_z(i, layer)
                color = QColor(layer.color)
                colors = {}
                for a, b, c, normal in layer.triangles:
                    if rotation.mapVector(QVector3D(*normal)).z() <= 0:
                        continue
                    points = [matrix.map(QVector3D(v[0], v[1], z + v[2] * thickness)) for v in (a, b, c)]
                    screen = QPolygonF([QPointF((v.x() + 1) * self.width() / 2,
                                                (1 - v.y()) * self.height() / 2) for v in points])
                    if not screen.boundingRect().intersects(self.rect().toRectF()):
                        continue
                    if normal not in colors:
                        colors[normal] = shade(color, normal)
                    faces.append((sum(v.z() for v in points), screen, colors[normal]))
            painter.setPen(Qt.NoPen)
            # Orthographic NDC depth increases away from the viewer.
            for _, screen, color in sorted(faces, key=lambda f: f[0], reverse=True):
                painter.setBrush(color)
                painter.drawPolygon(screen)
        painter.setRenderHint(QPainter.Antialiasing)
        self.hud(painter)
        painter.end()


def gl_format():
    fmt = QSurfaceFormat()
    fmt.setVersion(2, 1)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    return fmt


def opengl_available():
    if QApplication.platformName() in ('offscreen', 'minimal'):
        return False
    surface = QOffscreenSurface()
    surface.setFormat(gl_format())
    surface.create()
    context = QOpenGLContext()
    context.setFormat(surface.format())
    ok = context.create() and context.makeCurrent(surface)
    if ok:
        context.doneCurrent()
    surface.destroy()
    return bool(ok)


class OpenGLView(Camera, QOpenGLWidget):
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFormat(gl_format())
        self.setup_camera()
        self.buffers, self.program, self.error = [], None, ''
        self.dirty = True

    def initializeGL(self):
        self.context().aboutToBeDestroyed.connect(self.cleanup)
        self.program = QOpenGLShaderProgram()
        vertex = '''
            attribute vec3 position;
            attribute vec3 normal;
            uniform mat4 mvp;
            uniform float elevation;
            uniform float thickness;
            varying float illumination;
            void main() {
                vec3 p = vec3(position.xy, elevation + position.z * thickness);
                gl_Position = mvp * vec4(p, 1.0);
                illumination = 0.48 + 0.52 * max(0.0, dot(normal, vec3(0.3, -0.4, 0.8660254)));
            }
        '''
        fragment = '''
            #ifdef GL_ES
            precision mediump float;
            #endif
            uniform vec3 color;
            varying float illumination;
            void main() { gl_FragColor = vec4(color * illumination, 1.0); }
        '''
        if not (self.program.addShaderFromSourceCode(QOpenGLShader.Vertex, vertex)
                and self.program.addShaderFromSourceCode(QOpenGLShader.Fragment, fragment)
                and self.program.link()):
            self.error = self.program.log()
            QTimer.singleShot(0, lambda: self.failed.emit(self.error))
        self.dirty = True

    def cleanup(self):
        self.makeCurrent()
        for buffer, _ in self.buffers:
            buffer.destroy()
        self.buffers = []
        self.program = None
        self.dirty = True
        self.doneCurrent()

    def upload(self):
        for buffer, _ in self.buffers:
            buffer.destroy()
        self.buffers = []
        if self.mesh:
            for layer in self.mesh.layers:
                values = array('f')
                for a, b, c, normal in layer.triangles:
                    for vertex in (a, b, c):
                        values.extend((*vertex, *normal))
                buffer = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
                if not buffer.create() or not buffer.bind():
                    raise RuntimeError('Unable to allocate an OpenGL mesh buffer.')
                data = values.tobytes()
                buffer.allocate(data, len(data))
                buffer.release()
                self.buffers.append((buffer, len(values) // 6))
        self.dirty = False

    def paintGL(self):
        if self.error or not self.program:
            return
        try:
            gl = self.context().functions()
            gl.glClearColor(BACKGROUND.redF(), BACKGROUND.greenF(), BACKGROUND.blueF(), 1.)
            gl.glEnable(0x0B71)  # GL_DEPTH_TEST
            gl.glDepthFunc(0x0203)  # GL_LEQUAL
            gl.glClear(0x00004000 | 0x00000100)
            if self.dirty:
                self.upload()
            program = self.program
            program.bind()
            program.setUniformValue('mvp', self.matrix())
            for i, (buffer, count) in enumerate(self.buffers):
                layer = self.mesh.layers[i]
                if not layer.visible or not count:
                    continue
                z, thickness = self.layer_z(i, layer)
                color = QColor(layer.color)
                program.setUniformValue('elevation', float(z))
                program.setUniformValue('thickness', float(thickness))
                program.setUniformValue('color', QVector3D(color.redF(), color.greenF(), color.blueF()))
                buffer.bind()
                for name, offset in [('position', 0), ('normal', 12)]:
                    location = program.attributeLocation(name)
                    program.enableAttributeArray(location)
                    program.setAttributeBuffer(location, 0x1406, offset, 3, 24)  # GL_FLOAT
                gl.glDrawArrays(0x0004, 0, count)  # GL_TRIANGLES
                for name in ('position', 'normal'):
                    program.disableAttributeArray(program.attributeLocation(name))
                buffer.release()
            program.release()
            gl.glDisable(0x0B71)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            self.hud(painter)
            painter.end()
        except Exception as exc:
            self.error = str(exc)
            QTimer.singleShot(0, lambda: self.failed.emit(self.error))
