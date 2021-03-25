# -*- coding: utf-8 -*-
#
# mini_gland.py (Blender script)
#   Sets up an animation to "grow" parotid gland cells around (and within) duct constraints.
#
# J.rugis
#
# Blender python console:
#  filename = "/Users/jrug001/Desktop/nesi00119/mini-gland/mini_gland_striated_duct.py"
#  exec(compile(open(filename).read(), filename, 'exec'))
#
# Blender headless (Mac):
#  cd ~/Desktop/nesi00119/mini-gland
#  /Applications/Blender.app/Contents/MacOS/Blender --background --python mini_gland__striated_duct.py
#
# Python using blender import:
#  cd ~/Desktop/nesi00119/mini-gland
#  python3 mini_gland_striated_duct.py > log.txt
#
import bpy
import bmesh
import math
import mathutils
import numpy as np
import random

#-------------------------------------------------------------------------------
# class (structure) definitions
#-------------------------------------------------------------------------------

class cPts: # duct segment end-point structure
  def __init__(self, position):
    self.position = position
    
class cDseg: # duct segment structure
  def __init__(self, idx_out, idx_in, ctype):
    self.idx_out = idx_out
    self.idx_in = idx_in
    self.ctype = ctype

#-------------------------------------------------------------------------------
# global constants
#-------------------------------------------------------------------------------

main_collection = bpy.context.collection

# cell type dictionary
cell_types = {  
  "acinar"       : {"color":(1.000, 0.055, 0.060, 1.0), "pressure":1.8, "stiffness":0.20, "radii":(0.35, 16.3)},
  "intercalated" : {"color":(1.000, 0.100, 0.120, 1.0), "pressure":1.2, "stiffness":0.11, "radii":(0.8, 11.6)},
  "striated"     : {"color":(1.000, 0.200, 0.240, 1.0), "pressure":1.2, "stiffness":0.11, "radii":(4.0, 23.8)}    
}

# duct segment end-points: position
PTS = (
  cPts(mathutils.Vector((0.0, 0.0, 0.0))), 
  cPts(mathutils.Vector((0.0, 0.0, 40.0)))
  )

# duct segment connectivity
#   - final duct out segment listed first
#   - "upstream" (high to low radius) ordering
DSEG = (
  cDseg(0, 1, "striated"))

C_RADIUS = 2.3             # cell seed radius
EPSILON = 0.005            # a small numerical offset

#-------------------------------------------------------------------------------
# global variables
#-------------------------------------------------------------------------------

cell_centers = list()

#-------------------------------------------------------------------------------
# FUNCTION DEFINITIONS
#-------------------------------------------------------------------------------

#---- combine mesh objects using boolean union modifier
def combine(prev):
  bpy.ops.object.modifier_add(type = 'BOOLEAN')
  bpy.context.object.modifiers["Boolean"].operation = "UNION"
  bpy.context.object.modifiers["Boolean"].object = prev
  bpy.context.object.modifiers["Boolean"].double_threshold = 0.0
  bpy.ops.object.modifier_apply(modifier = "Boolean")
  current = bpy.context.object
  # delete previous object
  bpy.ops.object.select_all(action = 'DESELECT')
  prev.select_set(True) # required by bpy.ops
  bpy.ops.object.delete()
  return(current)

#---- create a duct segment given endpoints and radii
def create_seg(p1, p2, r1):
  d = (p2 - p1).length
  l = p1 + (p2 - p1) / 2.0
  r = (p2 - p1).to_track_quat('Z', 'X').to_euler()
  bpy.ops.mesh.primitive_cone_add(radius1 = r1, radius2 = r1, depth = d, location = l, rotation = r, end_fill_type = 'NGON')
  return

#---- create and combine duct segments
def create_duct_wall(in_out):
  prev = None

  # create duct segments
  s = DSEG
  p1 = PTS[s.idx_out].position
  p2 = PTS[s.idx_in].position
  r1 = cell_types[s.ctype]['radii'][in_out]

  # cylinder for non-acinar segments
  create_seg(p1, p2, r1)
  if not prev:
    prev = bpy.context.object
  else:
    prev = combine(prev)

  if in_out == 0:
    bpy.context.object.name = "InnerWall"
  else:
    bpy.context.object.name = "OuterWall"

  # remesh the duct object
  prev.select_set(True) # required by bpy.ops
  bpy.ops.object.modifier_add(type = 'REMESH')
  bpy.context.object.modifiers["Remesh"].mode = "SMOOTH"
  #bpy.context.object.modifiers["Remesh"].octree_depth = 7
  bpy.context.object.modifiers["Remesh"].octree_depth = 5
  bpy.ops.object.modifier_apply(modifier = "Remesh")
  if in_out == 1: # flip normals for outer duct wall
    bpy.ops.object.editmode_toggle()
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set()
  bpy.ops.object.modifier_add(type = 'COLLISION')
  bpy.data.collections['Duct'].objects.link(bpy.context.object)
  main_collection.objects.unlink(bpy.context.object) # unlink from main collection
  return

#---- new cell too close to any of the existing cells?
def too_close(p, dist):
  for c in cell_centers:
    if (p-c).length < dist:
      return True
  return False

#---- create cells around a duct segment
def create_seg_cells(s):
  mat = bpy.data.materials.new(name="mat")
  mat.diffuse_color = cell_types[s.ctype]["color"]

  z1 = PTS[s.idx_out].position.z
  z2 = PTS[s.idx_in].position.z

  #r1 = cell_types[s.ctype]['radii'][0] + ((cell_types[s.ctype]['radii'][1] - cell_types[s.ctype]['radii'][0]) / 6.0)  # near inner wall
  r1 = cell_types[s.ctype]['radii'][1] - 2.5 * C_RADIUS# near inner wall
  z12 = z2 - z1
  for i in range(120): # try to create this number of random cell seeds
    create = False
    for j in range(80000): # with many retries to help fill gaps in the seed distribution
      a1 = random.uniform(0.0, 2.0 * math.pi)
      # a duct cell seed placement point
      z = random.uniform(z1 + C_RADIUS, z2 - C_RADIUS) 
      p = mathutils.Vector((r1*math.sin(a1), r1*math.cos(a1), z))
      if len(cell_centers)==0 or not too_close(p, 3.0 * C_RADIUS): #   but accept only if not too close to other seeds
        create = True
        break
    if create:
      if j > 5000: print(j) # diagnostic: success with many retries?
      cell_centers.append(p)
      bpy.ops.object.duplicate()
      bpy.context.object.name = "Cell.001"    # duplicate names will auto increment
      bpy.context.object.data.materials[0] = mat #assign material to object
      bpy.context.object.location = p
      if s.ctype == "acinar": # an acinar cell seed placement point
        scale = random.uniform(0.90, 0.99)
      else:
        #scale = random.uniform(0.9, 1.1)
        scale = 1.0
      bpy.context.object.scale = (scale, scale, scale)
      bpy.context.object.modifiers["Cloth"].settings.uniform_pressure_force = cell_types[s.ctype]["pressure"]
      bpy.context.object.modifiers["Cloth"].settings.compression_stiffness = cell_types[s.ctype]["stiffness"]
  return

#---- create cells around all of the duct segments
def create_cells():
  #for s in DSEG:
  #  create_seg_cells(s)
  create_seg_cells(DSEG)
  return

#-------------------------------------------------------------------------------
#  MAIN PROGRAM
#-------------------------------------------------------------------------------

bpy.context.scene.gravity = (0,0,0) # turn gravity off

# create duct collection
bpy.context.scene.collection.children.link(bpy.data.collections.new(name = "Duct"))
create_duct_wall(0) # duct inner wall
create_duct_wall(1) # duct outer wall

# create cells collection
bpy.context.scene.collection.children.link(bpy.data.collections.new(name = "Cells"))

# create prototype cell
#bpy.ops.mesh.primitive_ico_sphere_add(subdivisions = 6, radius = C_RADIUS, location = (0.0, 0.0, 0.0))
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions = 4, radius = C_RADIUS, location = (0.0, 0.0, 0.0))
bpy.data.collections["Cells"].objects.link(bpy.context.object)
main_collection.objects.unlink(bpy.context.object) # unlink from main collection

mat = bpy.data.materials.new(name="mat")
bpy.context.object.data.materials.append(mat) # add material to object

bpy.ops.object.modifier_add(type = 'CLOTH')
bpy.context.object.modifiers["Cloth"].settings.use_internal_springs = False
bpy.context.object.modifiers["Cloth"].settings.use_pressure = True
bpy.context.object.modifiers["Cloth"].settings.tension_stiffness = 0.01

bpy.ops.object.modifier_add(type = 'COLLISION')

# duplicate prototype cell
create_cells()

# remove the prototype cell
bpy.data.objects.remove(bpy.data.objects['Icosphere'])

#-------------------------------------------------------------------------------
# for standalone version 
#-------------------------------------------------------------------------------

# animate (to apply physics) 
bpy.context.scene.frame_current = 1
for f in range(38):
  bpy.context.view_layer.update()
  bpy.context.scene.frame_current += 1

# save the duct and cell meshes in an obj file
for obj in bpy.data.collections["Duct"].all_objects: obj.select_set(False)
for obj in bpy.data.collections["Cells"].all_objects: obj.select_set(True)
bpy.ops.export_mesh.stl(filepath="sample.stl", use_selection=True)

#-------------------------------------------------------------------------------
# DEBUG: run interactive interpreter
#import__('code').interact(local=dict(globals(), **locals()))
#-------------------------------------------------------------------------------

#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
