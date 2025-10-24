import System
import clr
clr.AddReference("RevitNodes")
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB import FilteredElementCollector, Dimension
from Autodesk.Revit.DB.Architecture import *
clr.AddReference('RevitServices')
import RevitServices
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
from Autodesk.Revit.DB import DimensionType as dmt
from Revit.Elements import *
clr.ImportExtensions(RevitServices.Elements)



doc = DocumentManager.Instance.CurrentDBDocument
view = doc.ActiveView
sketch_plane = view.SketchPlane

# learn how to use with TRANSACTION

#using Autodesk.Revit.DB.SpatialElement to get all rooms
rooms = FilteredElementCollector(doc, view.Id).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements()
walls = FilteredElementCollector(doc, view.Id).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
DIM_FROM_SIZE = IN[0] #dimesion only if it is greater than {40cm} 
FEET_TO_CM = 30.48
MIN_DIFF_BETWEEN_2_DIM_SAME_ROOM = IN[1] #there cannot be 2 different dimesion in the same room & rotation with less than {6cm} diff
MINIMUM_SEGMENT_LENGTH = IN[2] #minimum size of wall to dimesion in {cm} 
is_override = IN[3] if IN[3] is not None else False


v_dims_lengths = [] #vertical dimesions sizes 
h_dims_lengths = [] #horizontal dimesions sizes
output = []
errors = []
dim_ids = []
count_sum_dims = 0
view__cropped_shape = []
DIM_FRONT_TYPE = "Dim 3 mm"

def get_linked_elements():
    # Collect all RevitLinkInstances in the document
    link_instances_collector = FilteredElementCollector(doc).OfClass(RevitLinkInstance).ToElements()

    for link_instance in link_instances_collector:
        # Get the linked document
        linked_doc = link_instance.GetLinkDocument()

        if linked_doc:
            # Apply a bounding box filter for elements visible in the active view
            # offset =15
            # view_bounding_box = view.CropBox
            # outline = Outline((view_bounding_box.Min - XYZ(offset, offset, offset)), (view_bounding_box.Max + XYZ(offset, offset, offset)))
            # bounding_box_filter = BoundingBoxIntersectsFilter(outline)
            global rooms
            global walls
            
            #z_floor = view.GenLevel.Elevation
            # output.append([z_floor, view_bounding_box.Max, view_bounding_box.Min])

            all_rooms = list(rooms)
            # Collect elements from the linked document that are within the bounding box
            all_rooms.extend(FilteredElementCollector(linked_doc).\
            OfCategory(BuiltInCategory.OST_Rooms)\
            .WhereElementIsNotElementType().ToElements())

            rooms = list(all_rooms)
            # output.append([room_to_name(room) for room in rooms])

             #WherePasses(bounding_box_filter)
            all_walls = list(walls)
            all_walls.extend(FilteredElementCollector(linked_doc).\
            OfCategory(BuiltInCategory.OST_Walls)\
            .WhereElementIsNotElementType().ToElements())

            walls = list(all_walls)


def point_is_between(point, curve, isvertical):
    if isvertical == 1:
        if point.Y > curve.GetEndPoint(0).Y and point.Y < curve.GetEndPoint(1).Y:
            return True
        elif point.Y < curve.GetEndPoint(0).Y and point.Y > curve.GetEndPoint(1).Y:
            return True
    elif isvertical == 0:
        if point.X > curve.GetEndPoint(0).X and point.X < curve.GetEndPoint(1).X:
            return True
        elif point.X < curve.GetEndPoint(0).X and point.X > curve.GetEndPoint(1).X:
            return True
    return False

def cant_be_dimension(boundary_curve1_line1, boundary_curve1_line2, boundary_curve2_line1, boundary_curve2_line2):
    cant_be_dimension1 = not lines_coordinates_can_be_dimension(boundary_curve1_line1, boundary_curve2_line1)
    cant_be_dimension2 = not lines_coordinates_can_be_dimension(boundary_curve1_line1, boundary_curve2_line2)
    cant_be_dimension3 = not lines_coordinates_can_be_dimension(boundary_curve1_line2, boundary_curve2_line1)
    cant_be_dimension4 = not lines_coordinates_can_be_dimension(boundary_curve1_line2, boundary_curve2_line2)

    return cant_be_dimension1 and cant_be_dimension2 and cant_be_dimension3 and cant_be_dimension4

def create_demo_dim(boundary_curve1_line1, boundary_curve1_line2, boundary_curve2_line1, boundary_curve2_line2):
    dim1_start = boundary_curve1_line1.GetEndPoint(0)
    dim1_end = XYZ(dim1_start.X, boundary_curve1_line2.GetEndPoint(0).Y, dim1_start.Z)
    dim2_start = boundary_curve2_line1.GetEndPoint(0)
    dim2_end = XYZ(dim2_start.X, boundary_curve2_line2.GetEndPoint(0).Y, dim2_start.Z)

    if not is_Line_Vertical(boundary_curve1_line1):
        dim1_end = XYZ(boundary_curve1_line2.GetEndPoint(0).X, dim1_start.Y, dim1_start.Z)
        dim2_end = XYZ(boundary_curve2_line2.GetEndPoint(0).X, dim2_start.Y, dim2_start.Z)

    dim_line1 = Line.CreateBound(dim1_start, dim1_end)
    dim_line2 = Line.CreateBound(dim2_start, dim2_end)
    return dim_line1, dim_line2



def is_overlapping_lines(line1, line2):
    is_vertical = not is_Line_Vertical(line1)
    is_overlap1 = point_is_between(line1.GetEndPoint(0), line2, is_vertical)
    is_overlap2 = point_is_between(line1.GetEndPoint(1), line2, is_vertical)
    is_overlap3 = point_is_between(line2.GetEndPoint(0), line1, is_vertical)
    is_overlap4 = point_is_between(line2.GetEndPoint(1), line1, is_vertical)

    return is_overlap1 or is_overlap2 or is_overlap3 or is_overlap4

def curves_need_connection(boundaries_dim1, boundaries_dim2):
    if boundaries_dim1 != None and boundaries_dim2 != None:
        boundary_curve1_line1 = boundaries_dim1[0]
        boundary_curve1_line2 = boundaries_dim1[1]

        boundary_curve2_line1 = boundaries_dim2[0]
        boundary_curve2_line2 = boundaries_dim2[1]

        is_vertical = not is_Line_Vertical(boundary_curve1_line1)

        if cant_be_dimension(boundary_curve1_line1, boundary_curve1_line2, boundary_curve2_line1, boundary_curve2_line2):
            return False

        dim_line1, dim_line2 = create_demo_dim(boundary_curve1_line1, boundary_curve1_line2, boundary_curve2_line1, boundary_curve2_line2)
        
        if is_overlapping_lines(dim_line1, dim_line2):
            return False


        
        offset = 0.0001

        dim_s = round(distance_between_lines(boundary_curve1_line1, boundary_curve1_line2)*FEET_TO_CM)
        dim_s2 = round(distance_between_lines(boundary_curve2_line1, boundary_curve2_line2)*FEET_TO_CM)

        a1 = boundary_curve1_line1.GetEndPoint(0).Y
        a2 = boundary_curve1_line2.GetEndPoint(0).Y
        b1 = boundary_curve2_line1.GetEndPoint(0).Y
        b2 = boundary_curve2_line2.GetEndPoint(0).Y
        l_ys = [a1, a2, b1, b2]
        # if is_vertical and (dim_s == 220 or dim_s2 == 220):
        #     output.append([dim_s, dim_s2, l_ys])
        # if is_vertical and (dim_s == 150 or dim_s2 == 150):
        #     output.append([dim_s, dim_s2, l_ys])

      
        
        if is_vertical == 1:
            if dif_less_then_minimum(boundary_curve1_line1.GetEndPoint(0).Y, boundary_curve2_line1.GetEndPoint(0).Y, offset):
                return True
            if dif_less_then_minimum(boundary_curve1_line1.GetEndPoint(0).Y, boundary_curve2_line2.GetEndPoint(0).Y, offset):
                return True
            if dif_less_then_minimum(boundary_curve1_line2.GetEndPoint(0).Y, boundary_curve2_line1.GetEndPoint(0).Y, offset):
                return True
            if dif_less_then_minimum(boundary_curve1_line2.GetEndPoint(0).Y, boundary_curve2_line2.GetEndPoint(0).Y, offset):
                return True
        elif is_vertical == 0:
            if dif_less_then_minimum(boundary_curve1_line1.GetEndPoint(0).X, boundary_curve2_line1.GetEndPoint(0).X, offset):
                return True
            if dif_less_then_minimum(boundary_curve1_line1.GetEndPoint(0).X, boundary_curve2_line2.GetEndPoint(0).X, offset):
                return True
            if dif_less_then_minimum(boundary_curve1_line2.GetEndPoint(0).X, boundary_curve2_line1.GetEndPoint(0).X, offset):
                return True
            if dif_less_then_minimum(boundary_curve1_line2.GetEndPoint(0).X, boundary_curve2_line2.GetEndPoint(0).X, offset):
                return True
            
    return False



def create_connected_dim(isVertical, points):
    coor = []
    if isVertical == 1:
        coor = [p.Y for p in points]
    elif isVertical == 0:
        coor = [p.X for p in points]

    if coor != []:
        max_value = max(coor)
        min_Value = min(coor)
        index_max = coor.index(max_value)
        index_min = coor.index(min_Value)
        start_point = points[index_min]
        end_point = points[index_max]
        # output.append(isVertical)
        if isVertical == 1:
            offset = XYZ(0.1 ,0 ,0)
            #output.append([start_point, end_point])
            bottom_line = Line.CreateBound((start_point + offset), (start_point - offset))
            top_line = Line.CreateBound((XYZ(start_point.X, end_point.Y, start_point.Z) + offset), (XYZ(start_point.X , end_point.Y, start_point.Z)- offset))

            create_dimension(bottom_line, top_line, -2)
        elif isVertical == 0:
            offset = XYZ(0 ,0.1 ,0)

            left_line = Line.CreateBound((start_point + offset), (start_point- offset))
            right_line = Line.CreateBound((XYZ(end_point.X, start_point.Y, start_point.Z) + offset), (XYZ(end_point.X , start_point.Y, start_point.Z)- offset))

            create_dimension(left_line, right_line, -2)

def boundaries_dim_to_points(boundaries):
    boundary_line1 = boundaries[0]
    boundary_line2 = boundaries[1]

    from_line = boundary_line1 if boundary_line1.Length <= boundary_line2.Length else boundary_line2 #smaller line
    to_line = boundary_line2 if from_line == boundary_line1 else boundary_line1
    
    line_curve1 = create_center_curve(from_line)
    line_curve2 = create_center_of_other(to_line, from_line)
    point_curve1 = get_center_xyz(line_curve1.GeometryCurve, False)
    point_curve2 = get_center_xyz(line_curve2.GeometryCurve, False)

    return [point_curve1, point_curve2]


    

     



def connect_broken_dims():
    doc = DocumentManager.Instance.CurrentDBDocument
    collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Dimensions)
    dimensions = collector.WhereElementIsNotElementType().ToElements()
    global dim_ids
    dims_created_now = [dim for dim in dimensions if dim.Id in dim_ids]

    dims_to_connect = []
    #ex: lenroom = [length, room, [2 segment boundaries]]
    for index, len_room in enumerate(h_dims_lengths):
        for len_room2 in h_dims_lengths[index+1:]:
            if len_room[1] != len_room2[1]: #not same room
                if curves_need_connection(len_room[2], len_room2[2]): #has exactly same y/x but different rooms
                    dims_to_connect.append([len_room, len_room2])
                    break
    

    for index, len_room in enumerate(v_dims_lengths):
        for len_room2 in v_dims_lengths[index+1:]:
            if len_room[1] != len_room2[1]: #not same room
                if curves_need_connection(len_room[2], len_room2[2]): #has exactly same y/x but different rooms
                    dims_to_connect.append([len_room, len_room2])
                    break

    ids_to_delete = []
    for len_rooms_curves in dims_to_connect:
        points = []
        for dim in len_rooms_curves:
            for real_dim in dims_created_now:
                below = real_dim.Below.split(' ') #[isvertical, room number]
            
                if dim[1] == int(below[1]): #same room
                    if (not is_Line_Vertical(dim[2][0]) == 0 and below[0] == "horizontal") or  (not is_Line_Vertical(dim[2][0]) == 1 and  below[0] == "vertical"): #same orietation
                            if int(real_dim.ValueOverride) + 5 == dim[0]: #same size
                                points.extend(boundaries_dim_to_points(dim[2]))
                                ids_to_delete.append(real_dim.Id) 
                                break
        create_connected_dim(not is_Line_Vertical(len_rooms_curves[0][2][0]), points)

    for id in ids_to_delete:
        TransactionManager.Instance.EnsureInTransaction(doc)
        try:
            doc.Delete(id)
        except:
            pass
        TransactionManager.Instance.TransactionTaskDone()




def filter_duplicates(dims_created_now):
    remove_duplicate = [] #list of duplicate dim {sizes, is vertical, room number}, with as many values as there is duplicates
    #ex: {1,1,1,1,2,2,2,3,4,4} output: {1,1,1,2,2,4}
    global h_dims_lengths
    global v_dims_lengths

    for index, len_room in enumerate(h_dims_lengths):
        for len_room2 in h_dims_lengths[index+1:]:
            if len_room[1] == len_room2[1]: #same room
                
                if len_room[0] == len_room2[0]: #same size
                    remove_duplicate.append([len_room[0], 0, len_room[1]])
                    break
    

    for index, len_room in enumerate(v_dims_lengths):
        for len_room2 in v_dims_lengths[index+1:]:
            if len_room[1] == len_room2[1]: #same room
                if len_room[0] == len_room2[0]: #same size
                    remove_duplicate.append([len_room[0], 1, len_room[1]]) #len, isvertical, room
                    break
    return remove_duplicate

def delete_below_text():
    doc = DocumentManager.Instance.CurrentDBDocument
    collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Dimensions)
    dimensions = collector.WhereElementIsNotElementType().ToElements()
    #dim_in_view = [dim for dim in dimensions if dim.View and dim.View.Id == doc.ActiveView.Id]
    global dim_ids
    dims_created_now = [dim for dim in dimensions if dim.Id in dim_ids]

    TransactionManager.Instance.EnsureInTransaction(doc)
    for dim in dims_created_now:
        dim.Below = ""
    TransactionManager.Instance.TransactionTaskDone()


def filter_small_diff_dim(dims_created_now):
   remove = []
   global h_dims_lengths
   global v_dims_lengths

   for index, len_room in enumerate(h_dims_lengths):
        for len_room2 in h_dims_lengths[index+1:]:
            if len_room[1] == len_room2[1]: #same room
                if dif_less_then_minimum(len_room[0], len_room2[0], MIN_DIFF_BETWEEN_2_DIM_SAME_ROOM): #diff less than min
                    remove.append([max(len_room[0], len_room2[0]), 0, len_room[1]])  #[len, isvertical, room]
                    if len_room[0] > len_room2[0]: #remove the larger dimension, smaller is from wall face 
                        h_dims_lengths.pop(index)
                    else:
                        h_dims_lengths.pop(index+1)

   for index, len_room in enumerate(v_dims_lengths):
        for len_room2 in v_dims_lengths[index+1:]:
            if len_room[1] == len_room2[1]: #same room
                if dif_less_then_minimum(len_room[0], len_room2[0], MIN_DIFF_BETWEEN_2_DIM_SAME_ROOM):#diff less than min
                    remove.append([max(len_room[0], len_room2[0]), 1, len_room[1]]) #[len, isvertical, room]
                    if len_room[0] > len_room2[0]:#remove the larger dimension, smaller is from wall face 
                        v_dims_lengths.pop(index)
                    else:
                        v_dims_lengths.pop(index+1)
    
   return remove
    

def get_center_xyz(line, isUp):
    x = (line.GetEndPoint(0).X + line.GetEndPoint(1).X)/2
    y = (line.GetEndPoint(0).Y + line.GetEndPoint(1).Y)/2
    z = (line.GetEndPoint(0).Z + line.GetEndPoint(1).Z)/2
    if isUp:
        x += (line.GetEndPoint(0).X - line.GetEndPoint(1).X)/50
        y += (line.GetEndPoint(0).Y - line.GetEndPoint(1).Y)/50
        z += (line.GetEndPoint(0).Z - line.GetEndPoint(1).Z)/50
    return XYZ(x,y,z)

def create_center_curve(line): #create a small line on the center of another (little bit above)
    center_line = Line.CreateBound(get_center_xyz(line, isUp = True), get_center_xyz(line, isUp = False))
    TransactionManager.Instance.EnsureInTransaction(doc)

    line_curve = doc.Create.NewModelCurve(center_line, sketch_plane) 

    #White color the temporal, Get the curve's graphics
    curve_gstyle = line_curve.LineStyle
    
    # Create a white color (255, 255, 255)
    white_color = Color(255, 255, 255)
    
    # Set the curve color to white
    curve_gstyle.GraphicsStyleCategory.LineColor = white_color

    TransactionManager.Instance.TransactionTaskDone()
    return line_curve

def create_center_of_other(line, line_center_from): #create a small line on line in front of the center of the smaller line
    #create the side of dimension on the bigger wall when walls aren't the same size 
    center = get_center_xyz(line_center_from, isUp = False)
    center_above = get_center_xyz(line_center_from, isUp = True)
    #points needed to be changed:
    center_to_change = get_center_xyz(line, isUp = False)
    center_above_to_change = get_center_xyz(line, isUp = False)

    if is_Line_Vertical(line) == 1:
        center_to_change = XYZ(center_to_change.X, center.Y, center_to_change.Z)
        center_above_to_change = XYZ(center_above_to_change.X, center_above.Y, center_above_to_change.Z)
    elif is_Line_Vertical(line) == 0:
        center_to_change = XYZ(center.X, center_to_change.Y, center_to_change.Z)
        center_above_to_change = XYZ(center_above.X, center_above_to_change.Y, center_above_to_change.Z)
    center_line = Line.CreateBound(center_to_change, center_above_to_change)
    TransactionManager.Instance.EnsureInTransaction(doc)
    line_curve = doc.Create.NewModelCurve(center_line, sketch_plane)
    # White color the temporal lines, Get the curve's graphics
    curve_gstyle = line_curve.LineStyle
    
    # Create a white color (255, 255, 255)
    white_color = Color(255, 255, 255)
    
    # Set the curve color to white
    curve_gstyle.GraphicsStyleCategory.LineColor = white_color
    TransactionManager.Instance.TransactionTaskDone()
    return line_curve
        

def delete_all_dimensions():
    collector = FilteredElementCollector(doc, view.Id).OfCategory(BuiltInCategory.OST_Dimensions)
    dimensions = collector.WhereElementIsNotElementType().ToElements()
    dim_ids = [dim.Id for dim in dimensions]


    TransactionManager.Instance.EnsureInTransaction(doc)
    for dim_id in dim_ids:
        doc.Delete(dim_id)
    TransactionManager.Instance.TransactionTaskDone()

def side_of_wall(segments): #determines the side of the room from the segments
    #finds the heighst y coordination of the horizontal segments 
    segments_horizontal = [segment for segment in segments if is_Line_Vertical(segment.GetCurve()) == 0]
    segments_y_coor = [segment.GetCurve().GetEndPoint(0).Y for segment in segments_horizontal]
    max_y = max(segments_y_coor)
    index_start = -1
    for i, segment in enumerate(segments):
        #find the index of it in the original list
        if segment.GetCurve().GetEndPoint(0).Y == max_y:
            index_start = i 
            break
    
    side_of_walls = [0]*len(segments)
    if index_start != -1:
        for i in range(index_start, index_start +len(segments)):
            #fill side_of_walls list same order of segements with the values of side of wall
            #the value of the previous side of wall effecting the value of the next
            index_segments = i % len(segments)
            index_last_segments = ((i-1) % len(segments))
            segment = segments[index_segments]
            last_segment = segments[index_last_segments]

            #if the current segment is above/below and right/left from the previous 
            isright = get_center_xyz(segment.GetCurve(), False).X > get_center_xyz(last_segment.GetCurve(), False).X
            isabove = get_center_xyz(segment.GetCurve(), False).Y > get_center_xyz(last_segment.GetCurve(), False).Y
            
            if i == index_start:
                side_of_walls[index_start] = "bottom"
            elif is_Line_Vertical(segment.GetCurve()) == is_Line_Vertical(last_segment.GetCurve()):
                side_of_walls[index_segments] = side_of_walls[index_last_segments]
            elif side_of_walls[index_last_segments] == "bottom":
                if (not isright and isabove) or (isright and not isabove):
                    side_of_walls[index_segments] = "left"
                else:
                    side_of_walls[index_segments] = "right"
            elif side_of_walls[index_last_segments] == "top":
                if (isright and isabove) or (not isright and not isabove):
                    side_of_walls[index_segments] = "left"
                else:
                    side_of_walls[index_segments] = "right"
            elif side_of_walls[index_last_segments] == "right":
                if (isright and isabove) or (not isright and not isabove):
                    side_of_walls[index_segments] = "bottom"
                else:
                    side_of_walls[index_segments] = "top"
            elif side_of_walls[index_last_segments] == "left":
                if (not isright and isabove) or (isright and not isabove):
                    side_of_walls[index_segments] = "bottom"
                else:
                    side_of_walls[index_segments] = "top"

        
    
    return list(zip(segments, side_of_walls))

def through_a_wall_face(line_element, line_element2):
    line1 = line_element[0]
    line2 = line_element2[0]
    if line_element[1] == line_element2[1]: #both line are at the same side of wall, dim must be through a wall
        return True 
    elif line_element[1] == "left" and line_element2[1] == "right":
        if line1.GetEndPoint(0).X <  line2.GetEndPoint(0).X:
            return True
    elif line_element[1] == "right" and line_element2[1] == "left":
          if line1.GetEndPoint(0).X > line2.GetEndPoint(0).X:
              return True
    elif line_element[1] == "top" and line_element2[1] == "bottom":
        if line1.GetEndPoint(0).Y > line2.GetEndPoint(0).Y:
            return True
    elif line_element[1] == "bottom" and line_element2[1] == "top":
        if line1.GetEndPoint(0).Y < line2.GetEndPoint(0).Y:
            return True
    return False
    
def lines_coordinates_can_be_dimension(line1, line2):
    offset = -2

    if  is_Line_Vertical(line1) == 1: #l1 all above or l1 all below  
        p1_start_above =  line1.GetEndPoint(0).Y > line2.GetEndPoint(0).Y + offset and line1.GetEndPoint(0).Y > line2.GetEndPoint(1).Y+ offset
        p1_end_above = line1.GetEndPoint(1).Y > line2.GetEndPoint(0).Y + offset and line1.GetEndPoint(1).Y > line2.GetEndPoint(1).Y+ offset
        p1_start_below =  line1.GetEndPoint(0).Y+ offset < line2.GetEndPoint(0).Y and line1.GetEndPoint(0).Y+ offset < line2.GetEndPoint(1).Y
        p1_end_below = line1.GetEndPoint(1).Y + offset< line2.GetEndPoint(0).Y and line1.GetEndPoint(1).Y+ offset < line2.GetEndPoint(1).Y
        if (p1_start_above and p1_end_above) or (p1_start_below and p1_end_below): #l1 (all above) or l1 (all below)  
            return False
    elif is_Line_Vertical(line1) == 0:
        p1_start_right =  line1.GetEndPoint(0).X > line2.GetEndPoint(0).X+ offset and line1.GetEndPoint(0).X > line2.GetEndPoint(1).X+ offset
        p1_end_rigth = line1.GetEndPoint(1).X > line2.GetEndPoint(0).X + offset and line1.GetEndPoint(1).X > line2.GetEndPoint(1).X+ offset
        p1_start_left =  line1.GetEndPoint(0).X+ offset < line2.GetEndPoint(0).X and line1.GetEndPoint(0).X+ offset < line2.GetEndPoint(1).X
        p1_end_left = line1.GetEndPoint(1).X+ offset < line2.GetEndPoint(0).X and line1.GetEndPoint(1).X+ offset < line2.GetEndPoint(1).X
        if (p1_start_right and p1_end_rigth) or (p1_start_left and p1_end_left):#l1 all right or l1 all left  
            return False
    else:
        return False
    return True
        


def create_5_possible_dim_between(line1, line2):
    possible_lines = []
    is_vertical = is_Line_Vertical(line1)

    #small line = the max line that have same coordinated between 2 boundaries
    small_line = None
    if is_vertical == 1:
        new_max = min(max(line1.GetEndPoint(0).Y, line1.GetEndPoint(1).Y), max(line2.GetEndPoint(0).Y, line2.GetEndPoint(1).Y))
        new_min = max(min(line1.GetEndPoint(0).Y, line1.GetEndPoint(1).Y), min(line2.GetEndPoint(0).Y, line2.GetEndPoint(1).Y))
        p_start_small_line = XYZ(line1.GetEndPoint(0).X, new_min, line1.GetEndPoint(0).Z)
        p_end_small_line = XYZ(line1.GetEndPoint(0).X, new_max, line1.GetEndPoint(0).Z)
        small_line = Line.CreateBound(p_start_small_line, p_end_small_line)
    elif is_vertical == 0:
        new_max = min(max(line1.GetEndPoint(0).X, line1.GetEndPoint(1).X), max(line2.GetEndPoint(0).X, line2.GetEndPoint(1).X))
        new_min = max(min(line1.GetEndPoint(0).X, line1.GetEndPoint(1).X), min(line2.GetEndPoint(0).X, line2.GetEndPoint(1).X))
        p_start_small_line = XYZ(new_min, line1.GetEndPoint(0).Y,  line1.GetEndPoint(0).Z)
        p_end_small_line = XYZ(new_max, line1.GetEndPoint(0).Y, line1.GetEndPoint(0).Z)
        small_line = Line.CreateBound(p_start_small_line, p_end_small_line)
    
    if small_line is not None:
        quater = float(small_line.Length/4) 
        offset = 0.5 #that the line created won't touch his boundaries
        for times in range(0,5):
            if is_vertical == 1:
                if small_line.GetEndPoint(0).X > line2.GetEndPoint(0).X:
                    offset = -offset
                start_p = XYZ(small_line.GetEndPoint(0).X + offset, small_line.GetEndPoint(0).Y + quater * times, small_line.GetEndPoint(0).Z)
                end_p = XYZ(line2.GetEndPoint(0).X - offset, small_line.GetEndPoint(0).Y + quater * times, small_line.GetEndPoint(0).Z)
                possible_lines.append(Line.CreateBound(start_p, end_p))
                output.append([start_p, end_p])
            elif is_vertical == 0:
                if small_line.GetEndPoint(0).Y > line2.GetEndPoint(0).Y:
                    offset = -offset
                start_p = XYZ(small_line.GetEndPoint(0).X + quater * times, small_line.GetEndPoint(0).Y + offset, small_line.GetEndPoint(0).Z)
                end_p = XYZ(small_line.GetEndPoint(0).X + quater * times, line2.GetEndPoint(0).Y - offset, small_line.GetEndPoint(0).Z)
                possible_lines.append(Line.CreateBound(start_p, end_p))
                output.append([start_p, end_p])
           
    return possible_lines
    

def line_intersection(lines, line2):
    count = 0 
    for line1 in lines:
        x1 = line1.GetEndPoint(0).X
        y1 = line1.GetEndPoint(0).Y
        x2 = line1.GetEndPoint(1).X
        y2 = line1.GetEndPoint(1).Y
        x3 = line2.GetEndPoint(0).X
        y3 = line2.GetEndPoint(0).Y
        x4 = line2.GetEndPoint(1).X
        y4 = line2.GetEndPoint(1).Y
        
        
        # Calculate the denominator
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        
        # If denominator is zero, lines are parallel
        if den == 0:
            return False
        
        # Calculate the intersection point
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
        
        # Check if intersection point lies on both line segments
        if 0 <= t <= 1 and 0 <= u <= 1:
            # output.append(["line1:",(x1, y1, x2, y2),"line2:", (x3, y3, x4, y4)])
            count += 1
    if count == 5:
        return True
    return False
  
    
def through_a_wall(line1, line2, dimension_lines):
    possible_dims = create_5_possible_dim_between(line1, line2)
    for lines_in_room in dimension_lines:
        for line_element in lines_in_room:
            if line_intersection(possible_dims, line_element[0]):
                return True
    return False



def need_dimension(line_element, line_element2, dimension_lines): #the lines are parralel and can be connected by perpendicular line (90 degrees)
    line1 = line_element[0]
    line2 = line_element2[0]
    if not lines_coordinates_can_be_dimension(line1, line2):
        return False
    #minimum wall size to dimesion from
    if round((line1.Length)*FEET_TO_CM) < MINIMUM_SEGMENT_LENGTH or round((line2.Length)*FEET_TO_CM) < MINIMUM_SEGMENT_LENGTH:
        return False
    #only relavant if dim is larger than DIM_FROM_SIZE
    if round((distance_between_lines(line1, line2)) * FEET_TO_CM) < DIM_FROM_SIZE:  
        return False
    if through_a_wall_face(line_element, line_element2):
        return False
    if through_a_wall(line1, line2, dimension_lines):
        return False
    return True


def create_dimension(line1, line2, room_num):
    TransactionManager.Instance.EnsureInTransaction(doc)
    #create a line from the center of the smaller one to the second wall
    from_line = line1 if line1.Length <= line2.Length else line2
    to_line = line2 if from_line == line1 else line1
    
    line_curve1 = create_center_curve(from_line)
    line_curve2 = create_center_of_other(to_line, from_line)
    # point_curve1 = line_curve1.GeometryCurve.GetEndPoint(0)
    # point_curve2 = line_curve2.GeometryCurve.GetEndPoint(0)

    
    dim_line_boundaries = [line1, line2]
    
    #second option is to color it in the end only the short lines

    ref_array = ReferenceArray() #ref array for dimension
    ref_array.Append(Reference(line_curve1))
    ref_array.Append(Reference(line_curve2))
    #create dimension
    dim = doc.Create.NewDimension(view, from_line, ref_array)
    global count_sum_dims
    count_sum_dims += 1
    global dim_ids
    dim_ids.append(dim.Id)
    dimesion_length = int(round(distance_between_lines(line1, line2)*30.48))
    if room_num >= 0: #inside room dim and not front of appartment
        dimesion_length =  dimesion_length - 5  # Decrease the value by 5
        isvertical = "vertical " + str(room_num)
        if is_Line_Vertical(from_line) == 1:
            isvertical = "horizontal " + str(room_num)
        dim.Below = isvertical #sets temporarly extra info, ver/hor & room num
        dim.ValueOverride = str(dimesion_length)  # Set the new length as a string
    elif room_num == -2: #connected dims after all filters 
        dimesion_length =  dimesion_length - 5  # Decrease the value by 5
        dim.ValueOverride = str(dimesion_length)  # Set the new length as a string
    else: #front to street dim
        # Get all dimension types
       dim_types = FilteredElementCollector(doc).OfClass(dmt).ToElements()
       #output.append([d.Name for d in dim_types if d.Name])
    #    dim_type_3mm_style = next((st for st in dim_types if st.Name == DIM_FRONT_TYPE), None)
    #    if dim_type_3mm_style:
    #             dim.ChangeTypeId(dim_type_3mm_style.Id)
    TransactionManager.Instance.TransactionTaskDone()
    # Get the geometry curve of the dimension

    return dim_line_boundaries

    

def is_Line_Vertical(line):
   if round(line.GetEndPoint(0).X, 3) == round(line.GetEndPoint(1).X, 3): #Xstart & Xend are the same, it is Vertical
      return 1
   elif round(line.GetEndPoint(0).Y, 3) == round(line.GetEndPoint(1).Y, 3): #Ystart & Yend are the same, it is Horizontal
      return 0
   else:
      return -1 #diagonal

def distance_between_lines(line, line2):
    if is_Line_Vertical(line) == 1:
        return abs(line.GetEndPoint(0).X-line2.GetEndPoint(0).X)
    elif is_Line_Vertical(line) == 0:
        return abs(line.GetEndPoint(0).Y-line2.GetEndPoint(0).Y)

def dif_less_then_minimum(length, length2, min):
    if length < length2 and length + min > length2: 
        return True
    if length > length2 and length - min < length2:
        return True
    return False

def update_crop_shape():
     # Check if the view has a non-rectangular crop
    if not view.CropBoxActive or view.CropBoxVisible:
        errors.append("No crop view found")
    
    # Get the crop shape
    crop_manager = view.GetCropRegionShapeManager()
    crop_shape = crop_manager.GetCropShape()
    
    if crop_shape is None or len(crop_shape) == 0:
        errors.append("No crop view found")
    
    # The crop shape is a list of curves
    global view__cropped_shape 
    view__cropped_shape.extend(crop_shape)

def room_to_name(room):
    if room and room.get_Parameter(BuiltInParameter.ROOM_NAME):
        room_name = room.get_Parameter(BuiltInParameter.ROOM_NAME).AsString().strip()
        room_name = room_name.replace('"',"")
        return room_name
    return ""



def is_in_cropped_view(point):
    global view__cropped_shape

    # Ray casting algorithm
    count = 0
    for curve in view__cropped_shape[0]:
        p1 = curve.GetEndPoint(0)
        p2 = curve.GetEndPoint(1)
        if ((p1.Y > point.Y) != (p2.Y > point.Y)) and \
           (point.X < (p2.X - p1.X) * (point.Y - p1.Y) / (p2.Y - p1.Y) + p1.X):
            count += 1
    return count % 2 == 1

def get_center_wall(wall):
    wall_bb = wall.get_BoundingBox(None)
    wall_center = XYZ(((wall_bb.Max.X + wall_bb.Min.X) / 2), ((wall_bb.Max.Y + wall_bb.Min.Y) / 2), ((wall_bb.Max.Z + wall_bb.Min.Z) / 2))
    return wall_center


def order_walls_list(walls):
    walls_in_floor = [wall for wall in walls if wall.LevelId == view.GenLevel.Id]
    walls_in_appartment = [wall for wall in walls_in_floor if is_in_cropped_view(get_center_wall(wall))]
    return walls_in_appartment
     
def room_not_in_appartment(room):
    z_floor = view.GenLevel.Elevation
    # output.append([room.Location.Point  , z_floor])
    if room.Location.Point.Z != z_floor:
        return True
    
    room_name = room_to_name(room)
    rooms_outside = ["מבואה", "לובי", "חדר מדרגות", "מעליות"]
    for room_outside in rooms_outside:
        if room_outside in room_name:
            return True
    return False

def empty_room(room):
    if not room:
        return True
    elif room.get_BoundingBox(doc.ActiveView) == None:
        return True
    elif room.Location == None or room.Location.Point == None:
        return True
    elif room.get_Parameter(BuiltInParameter.ROOM_NAME) == None or room.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() == "":
        return True
    else:
        return False

def order_rooms_list(rooms): #delete empty & duplicate
   rooms_not_empty = [room for room in rooms if not empty_room(room)] #delete empty
    
   #remove rooms that are not in the appartment
   rooms_in_view = [room for room in rooms_not_empty if is_in_cropped_view(room.Location.Point)]

   rooms_in_appartment = [room for room in rooms_in_view if not room_not_in_appartment(room)]
    #    output.append(rooms_in_appartment)


   rooms_locations = [room.Location.Point for room in rooms_in_appartment]
    #delete duplicate rooms with same locations
   rooms_not_duplicate = [room for index, room in enumerate(rooms_in_appartment) if room.Location.Point not in rooms_locations[:index]]

   return rooms_not_duplicate


def wall_is_balcony_or_garden(wall):
    room_height_cm = 0
    z_level = doc.ActiveView.GenLevel.Elevation
    wall_bb = wall.get_BoundingBox(None)

    if rooms != []:
        room_height = rooms[0].get_BoundingBox(None).Max.Z - rooms[0].get_BoundingBox(None).Min.Z
        room_height_cm = round(room_height * FEET_TO_CM)
        wall_height_cm =  round((wall_bb.Max.Z - wall_bb.Min.Z) * FEET_TO_CM)
        #if the height of a wall is below 80cm and more from a room[0] height its probably a balcony/garden wall 
        if wall_height_cm < (room_height_cm - 50): 
            return True
        
    wall_center = XYZ(((wall_bb.Max.X + wall_bb.Min.X) / 2), ((wall_bb.Max.Y + wall_bb.Min.Y) / 2), z_level)
    off_sets = [XYZ(2,0,0), XYZ(-2,0,0), XYZ(0,2,0), XYZ(0,-2,0)]
    for off_set in off_sets:
        room = doc.GetRoomAtPoint(wall_center + off_set)
        if room and room is not None:
            if "מרפסת" in room_to_name(room):
                return True
            if "חצר" in room_to_name(room):
                return True
    return False



def dim_front_of_appartment(walls):
    x_coordinates = []
    y_coordinates = []
    z_level = doc.ActiveView.GenLevel.Elevation

    if len(walls) == 0:
        return
    for wall in walls:
        if not wall_is_balcony_or_garden(wall):
            wall_bb = wall.get_BoundingBox(None)
            wall_min = wall_bb.Min
            wall_max = wall_bb.Max
            if is_in_cropped_view(wall_min):
                x_coordinates.append(wall_min.X)
                y_coordinates.append(wall_min.Y)
            if is_in_cropped_view(wall_max):
                x_coordinates.append(wall_max.X)
                y_coordinates.append(wall_max.Y)
    
    left_side_coor = min(x_coordinates)
    right_side_coor = max(x_coordinates)
    top_side_coor = max(y_coordinates)
    bottom_side_coor = min(y_coordinates)

    #detect the 2 front side, where a little     bit out of crop there is no room in point
    #where_is_front(left_side_coor, right_side_coor, top_side_coor, bottom_side_coor, z_level)
    width_front_max = Line.CreateBound(XYZ(right_side_coor, top_side_coor, z_level), XYZ(right_side_coor, top_side_coor - 5, z_level))
    width_front_min = Line.CreateBound(XYZ(left_side_coor, top_side_coor, z_level), XYZ(left_side_coor, top_side_coor - 5, z_level))

    create_dimension(width_front_min, width_front_max, -1)

    length_front_max = Line.CreateBound(XYZ(right_side_coor, top_side_coor, z_level), XYZ(right_side_coor - 5, top_side_coor, z_level))
    length_width_min = Line.CreateBound(XYZ(right_side_coor, bottom_side_coor, z_level), XYZ(right_side_coor - 5, bottom_side_coor, z_level))
    create_dimension(length_width_min, length_front_max, -1)


def get_v_h_lines(rooms):
    horizon_lines = [] #[room[segments_curve,segments_curve2],room2...]
    vertical_lines = []
    #get all room, and then, segments (walls) and seperaate to vertical and horizontal
    #get all room 
    for room in rooms:
        room_vertical = []
        room_horizontal = []
        #get all segments from rooms, same as walls
        boundaries = room.GetBoundarySegments(SpatialElementBoundaryOptions())
        if boundaries:
            for segments in boundaries:
                segments_side_of_wall = side_of_wall(segments) #attach the sideofwall to every segments of room
                # is_ver_list = [is_Line_Vertical(segment.GetCurve()) for segment in segments]
                #output.append([room_to_name(room), len(segments), is_ver_list])
                for segment_element in segments_side_of_wall:
                    segment_curve = segment_element[0].GetCurve()
                    if is_Line_Vertical(segment_curve) == 1:
                        #output.append(side_of_wall(True, segment.GetCurve(), room))
                        room_vertical.append([segment_curve, segment_element[1], room]) #add all v lines in a room to list
                    elif is_Line_Vertical(segment_curve) == 0:
                        room_horizontal.append([segment_curve, segment_element[1], room]) #add all h lines in a room to list
        #create 2 lists v and h of rooms and inside them lists of walls, list[room[wall, wall],..]
        vertical_lines.append(room_vertical)
        horizon_lines.append(room_horizontal)  
    return horizon_lines, vertical_lines

def creates_all_dimensions(dimension_lines, isVertical):
    #for every segment check if need to create dimesion to all other parralel segments in same room 
    for room_num, lines_in_room in enumerate(dimension_lines):
        for index, line_element  in enumerate (lines_in_room): #v_line_element = [curve, side on the wall]
            for line_element2 in lines_in_room[index+1:]: #not with himself, and only items after him, simetrical act
                if need_dimension(line_element, line_element2, dimension_lines): #2 vertical walls need to the same Ys to be dimesioned between, & minumun dim size
                        #from vertical segments\walls you create horizontal dims
                        dim_line_boundaries = create_dimension(line_element[0], line_element2[0], room_num)
                        if isVertical:
                            h_dims_lengths.append([round(distance_between_lines(line_element[0], line_element2[0])* FEET_TO_CM), room_num, dim_line_boundaries])
                        else:
                            v_dims_lengths.append([round(distance_between_lines(line_element[0], line_element2[0])* FEET_TO_CM), room_num, dim_line_boundaries])

def filter_dimensions():
    #gets all dimensions that created now
    doc = DocumentManager.Instance.CurrentDBDocument
    TransactionManager.Instance.EnsureInTransaction(doc)
    collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Dimensions)
    dimensions = collector.WhereElementIsNotElementType().ToElements()
    global dim_ids
    dims_created_now = [dim for dim in dimensions if dim.Id in dim_ids]   
    #get all the dimensions length to delete
    lengths_to_delete = []
    #checks for duplicate dimesions values in the same room and rotation and delete them
    lengths_to_delete.append(list(filter_duplicates(dims_created_now)))

    #checks for dimesions with the same size by offset of MIN_DIFF_BETWEEN_2_DIM_SAME_ROOM and delete them 
    lengths_to_delete.append(list(filter_small_diff_dim(dims_created_now)))
    

    lengths_to_delete = list(lengths_to_delete[0] + lengths_to_delete[1])
    #delete every dim to delete
    for dim in dims_created_now:
        below = dim.Below.split(' ') #[isvertical, room number]
        for len_del in lengths_to_delete:
            if len_del[2] == int(below[1]): #same room
                if (len_del[1] == 0 and  below[0] =="horizontal") or  (len_del[1] == 1 and  below[0] == "vertical"): #same orietation
                        if int(dim.ValueOverride) + 5 == len_del[0]: #same size
                            try:
                                lengths_to_delete.remove(len_del)
                            except:
                                pass
                            doc.Delete(dim.Id)
                            break   

   
if True: # if __name__ == "__main__":
    # Check if the active view is a floor plan view
    if not isinstance(doc.ActiveView, ViewPlan):
        errors.append("Please run this script in a floor plan view.")
    else:
        update_crop_shape()
        if is_override:
            delete_all_dimensions()

        get_linked_elements()
        rooms = order_rooms_list(rooms) #delete empty & duplicate
        walls = order_walls_list(walls) #takes only from same level

        horizon_lines, vertical_lines = get_v_h_lines(rooms)

        creates_all_dimensions(vertical_lines, True)
        creates_all_dimensions(horizon_lines, False)
        
        filter_dimensions()

        connect_broken_dims()

        delete_below_text()  

        dim_front_of_appartment(walls)

        output.append(str(count_sum_dims + 2) + " dimensions created")

        output.append(errors)

OUT = output
