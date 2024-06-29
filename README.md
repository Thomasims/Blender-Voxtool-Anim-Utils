This addon adds a few useful import/export functions to blender for dealing with Teardown/VoxTool animation files.

### Animations Export (`File > Export > VoxTool Animations (.fbx)`)
This tool lets you export all the actions in your project aswell as a "t-pose" reference into a folder.

Yoou can use the generated files in the VoxTool animation tab:
  - `_reference.fbx`: "T-Pose file"
  - `*.fbx`: "Add Sequence"

Make sure to set the sampling rates in Blender and VoxTool agree!

### Bonemap Export (`File > Export > VoxTool Bonemap (.xml)`)
This tool will export the selected armature as a VoxTool-compatible bonemap XML and corresponding vox file.

Using these files in VoxTool's animation tab rather than hand-crafted counterparts will result in a prefab with one voxel positioned at each bone:
  - `<filename>.xml`: "Bone mapping file"
  - `<filename>.xml.vox`: "T-Pose Vox file"

You can then modify this generated prefab in the in-game editor using the voxels as reference points.

### Animdata Import (`File > Import > VoxTool Animdata (.xml)`)
This tool lets you extract the armature (TODO: extract animations) from an Animdata file in XML format.

This is generally only useful if you're attempting to modify someone else's animation files where you don't have access to the source files.
