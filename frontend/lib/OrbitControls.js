/**
 * Minimal OrbitControls replacement for Three.js r152
 * Implements: rotate, zoom, pan
 */
THREE.OrbitControls = function(camera, domElement) {
  this.camera = camera;
  this.domElement = domElement;
  this.enabled = true;
  this.target = new THREE.Vector3(0, 0, 0);

  var scope = this;
  var STATE = { NONE: -1, ROTATE: 0, ZOOM: 1, PAN: 2 };
  var state = STATE.NONE;

  var spherical = new THREE.Spherical();
  var sphericalDelta = new THREE.Spherical();
  var panOffset = new THREE.Vector3();
  var scale = 1;

  // 初始状态
  var rotateStart = new THREE.Vector2();
  var panStart = new THREE.Vector2();

  function getZoomScale() { return Math.pow(0.95, 1); }

  this.update = function() {
    var offset = new THREE.Vector3();
    var quat = new THREE.Quaternion().setFromUnitVectors(camera.up, new THREE.Vector3(0, 1, 0));
    var quatInverse = quat.clone().invert();

    return function() {
      offset.copy(camera.position).sub(scope.target);
      offset.applyQuaternion(quat);
      spherical.setFromVector3(offset);

      spherical.theta += sphericalDelta.theta;
      spherical.phi += sphericalDelta.phi;
      spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi));
      spherical.radius *= scale;
      spherical.radius = Math.max(0.5, Math.min(20, spherical.radius));

      scope.target.add(panOffset);

      offset.setFromSpherical(spherical);
      offset.applyQuaternion(quatInverse);

      camera.position.copy(scope.target).add(offset);
      camera.lookAt(scope.target);

      sphericalDelta.theta = 0;
      sphericalDelta.phi = 0;
      scale = 1;
      panOffset.set(0, 0, 0);
    };
  }();

  function onMouseDown(event) {
    if (!scope.enabled) return;
    event.preventDefault();
    if (event.button === 0) {
      state = STATE.ROTATE;
      rotateStart.set(event.clientX, event.clientY);
    } else if (event.button === 1) {
      state = STATE.ZOOM;
    } else if (event.button === 2) {
      state = STATE.PAN;
      panStart.set(event.clientX, event.clientY);
    }
    document.addEventListener('mousemove', onMouseMove, false);
    document.addEventListener('mouseup', onMouseUp, false);
  }

  function onMouseMove(event) {
    if (!scope.enabled) return;
    if (state === STATE.ROTATE) {
      var dx = event.clientX - rotateStart.x;
      var dy = event.clientY - rotateStart.y;
      sphericalDelta.theta -= 2 * Math.PI * dx / domElement.clientHeight;
      sphericalDelta.phi -= 2 * Math.PI * dy / domElement.clientHeight;
      rotateStart.set(event.clientX, event.clientY);
    } else if (state === STATE.ZOOM) {
      var dy = event.clientY - rotateStart.y;
      scale *= Math.pow(0.95, dy > 0 ? 1 : -1);
      rotateStart.set(event.clientX, event.clientY);
    } else if (state === STATE.PAN) {
      var dx = event.clientX - panStart.x;
      var dy = event.clientY - panStart.y;
      var panSpeed = 0.01;
      var offset = new THREE.Vector3();
      offset.copy(camera.position).sub(scope.target);
      var targetDistance = offset.length();
      var fov = camera.fov || 50;
      var panDist = 2 * targetDistance * Math.tan(fov * Math.PI / 360) / domElement.clientHeight;
      var panLeft = new THREE.Vector3();
      panLeft.setFromMatrixColumn(camera.matrix, 0);
      panLeft.multiplyScalar(-dx * panDist);
      panOffset.add(panLeft);
      var panUp = new THREE.Vector3();
      panUp.setFromMatrixColumn(camera.matrix, 1);
      panUp.multiplyScalar(dy * panDist);
      panOffset.add(panUp);
      panStart.set(event.clientX, event.clientY);
    }
    scope.update();
  }

  function onMouseUp() {
    state = STATE.NONE;
    document.removeEventListener('mousemove', onMouseMove, false);
    document.removeEventListener('mouseup', onMouseUp, false);
  }

  function onWheel(event) {
    if (!scope.enabled) return;
    event.preventDefault();
    if (event.deltaY < 0) {
      scale /= Math.pow(0.95, 1);
    } else {
      scale *= Math.pow(0.95, 1);
    }
    scope.update();
  }

  domElement.addEventListener('mousedown', onMouseDown, false);
  domElement.addEventListener('wheel', onWheel, { passive: false });
  // 禁止右键菜单
  domElement.addEventListener('contextmenu', function(e) { e.preventDefault(); }, false);

  this.update();
  return this;
};
