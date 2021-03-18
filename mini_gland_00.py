# -*- coding: utf-8 -*-
#
# mini_gland.py (Blender script)
#   Sets up an animation to "grow" parotid gland cells around (and within) duct constraints.
#
# J.rugis
#
# Blender python console:
#  filename = "/Users/jrug001/Desktop/nesi00119/mini-gland/mini_gland_00.py"
#  exec(compile(open(filename).read(), filename, 'exec'))
#
# Blender headless (Mac):
#  cd ~/Desktop/nesi00119/mini-gland
#  /Applications/Blender.app/Contents/MacOS/Blender --background --python mini_gland_00.py
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
  def __init__(self, position, radius):
    self.position = position
    self.radius = radius
    
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
  "acinar"       : {"color":(1.000, 0.055, 0.060, 1.0), "pressure":1.8, "stiffness":0.20},
  "intercalated" : {"color":(1.000, 0.100, 0.120, 1.0), "pressure":1.2, "stiffness":0.11},
  "striated"     : {"color":(1.000, 0.200, 0.240, 1.0), "pressure":1.2, "stiffness":0.11}    
}

# duct segment end-points: position, radius
PTS = (
  cPts(mathutils.Vector((0.0, 0.0, 0.0)), 4.0), 
  cPts(mathutils.Vector((0.0, 0.0, 10.0)), 3.7), 
  cPts(mathutils.Vector((0.0, 0.0, 20.0)), 1.5),
  cPts(mathutils.Vector((0.0, 0.0, 40.0)), 1.5),
  cPts(mathutils.Vector((0.0, 0.0, 45.0)), 0.7), 
  cPts(mathutils.Vector((0.0, 0.0, 52.0)), 0.05))

# duct segment connectivity
#   - final duct out segment listed first
#   - "upstream" (high to low radius) ordering
DSEG = (
  cDseg(0, 1, "striated"),
  cDseg(1, 2, "striated"),
  cDseg(2, 3, "intercalated"),
  cDseg(3, 4, "intercalated"),
  cDseg(4, 5, "acinar"))

C_RADIUS = 1               # cell seed radius
C_OFFSET = 1.5 * C_RADIUS  # cell seed radial offset from inner duct wall
A_RADIUS = 8.0            # radius of acinii 
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
def create_seg(p1, r1, p2, r2):
  d = (p2 - p1).length
  l = p1 + (p2 - p1) / 2.0
  r = (p2 - p1).to_track_quat('Z', 'X').to_euler()
  bpy.ops.mesh.primitive_cone_add(radius1 = r1, radius2 = r2, depth = d, location = l, rotation = r, end_fill_type = 'NGON')
  return

#---- create and combine duct segments
def create_duct(offset):
  prev = None

  # create duct segments
  for s in DSEG:
    p1 = PTS[s.idx_out].position
    r1 = PTS[s.idx_out].radius + offset
    p2 = PTS[s.idx_in].position
    if not(offset == 0) and s.ctype == "acinar": # outer wall of acinus?
      r2 = A_RADIUS                      # use acinii radius
    else:   
      r2 = PTS[s.idx_in].radius + offset # use duct wall radius

    # sphere (in)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions = 4, radius = (1.0 + EPSILON)*r2, location = p2)
    if not(offset == 0) and s.ctype == "acinar": # outer wall of acinus?
      bpy.context.object.scale = (1.0,1.0,1.5)
    if not prev:
      prev = bpy.context.object
    else:
      prev = combine(prev)

    # cone
    create_seg(p1, r1, p2, r2)
    prev = combine(prev)

  if offset == 0:
    bpy.context.object.name = "InnerWall"
  else:
    bpy.context.object.name = "OuterWall"

  # remesh the duct object
  prev.select_set(True) # required by bpy.ops
  bpy.ops.object.modifier_add(type = 'REMESH')
  bpy.context.object.modifiers["Remesh"].mode = "SMOOTH"
  bpy.context.object.modifiers["Remesh"].octree_depth = 7
  bpy.ops.object.modifier_apply(modifier = "Remesh")
  if not offset == 0: # flip normals for outer duct wall
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
  r1 = PTS[s.idx_out].radius + C_OFFSET
  r2 = PTS[s.idx_in].radius + C_OFFSET
  r12 = r2 - r1
  z12 = z2 - z1
  for i in range(50): # try to create this number of random cell seeds
    create = False
    for j in range(10000): # with many retries to help fill gaps in the seed distribution
      a1 = random.uniform(0.0, 2.0 * math.pi)
      if s.ctype == "acinar": # an acinar cell seed placement point
        a2 = random.uniform(0.0, 0.8 * math.pi) # spherical distribution, but don't cover the duct
        r = 3.5 * C_RADIUS
        p = PTS[s.idx_in].position + mathutils.Vector((r*math.sin(a2)*math.cos(a1), r*math.sin(a2)*math.sin(a1), 1.5 * r*math.cos(a2))) 
        if len(cell_centers)==0 or not too_close(p, 2.8 * C_RADIUS): #   but accept only if not too close to other seeds
          create = True
          break
      else:                    # a duct cell seed placement point
        z = random.uniform(z1 + C_RADIUS, z2) # not the correct distribution for cones but it doesn't really matter
        r = random.uniform(0.95,1.05) * (((z-z1)/z12)*r12 + r1) # follow the duct segment cone radius
        p = mathutils.Vector((r*math.sin(a1), r*math.cos(a1), z))
        if len(cell_centers)==0 or not too_close(p, 2.5 * C_RADIUS): #   but accept only if not too close to other seeds
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
        scale = random.uniform(0.9, 1.1)
      bpy.context.object.scale = (scale, scale, scale)
      bpy.context.object.modifiers["Cloth"].settings.uniform_pressure_force = cell_types[s.ctype]["pressure"]
      bpy.context.object.modifiers["Cloth"].settings.compression_stiffness = cell_types[s.ctype]["stiffness"]
  return

#---- create cells around all of the duct segments
def create_cells():
  for s in DSEG:
    create_seg_cells(s)
  return

#-------------------------------------------------------------------------------
#  MAIN PROGRAM
#-------------------------------------------------------------------------------

bpy.context.scene.gravity = (0,0,0) # turn gravity off

# create duct collection
bpy.context.scene.collection.children.link(bpy.data.collections.new(name = "Duct"))
create_duct(0.0)             # duct inner wall
create_duct(2.0 * C_OFFSET)  # duct outer wall

# create cells collection
bpy.context.scene.collection.children.link(bpy.data.collections.new(name = "Cells"))

# create prototype cell
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions = 5, radius = C_RADIUS, location = (0.0, 0.0, 0.0))
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
#bpy.context.scene.frame_current = 1
#for f in range(9):
#  bpy.context.view_layer.update()
#  bpy.context.scene.frame_current += 1

# save the duct and cell meshes in an obj file
#for obj in bpy.data.collections["Duct"].all_objects: obj.select_set(False)
#for obj in bpy.data.collections["Cells"].all_objects: obj.select_set(True)
#bpy.ops.export_scene.obj(filepath="sample.obj", use_selection=True)

#-------------------------------------------------------------------------------
# DEBUG: run interactive interpreter
#import__('code').interact(local=dict(globals(), **locals()))
#-------------------------------------------------------------------------------

#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
