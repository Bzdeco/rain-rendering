from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, List, Tuple

import xml.etree.ElementTree as ET

import numpy as np
import shapely
from shapely.geometry import Polygon, LineString

from common.pose import CameraPose
from config.utils import parse_pose


def _combine_xml_annotation_files(annotations_folder: Path) -> ET.Element:
    annotations_xml = None

    for filepath in annotations_folder.glob("*"):
        if filepath.name == ".DS_Store":
            continue

        xml_root = ET.parse(filepath).getroot()
        if annotations_xml is None:
            annotations_xml = xml_root
        else:
            annotations_xml.extend(xml_root)

    return annotations_xml


def _fix_relative_image_path(image_node: ET.Element) -> Path:
    image_path = Path(image_node.attrib["name"])
    parents = list(image_path.parents)
    if len(parents) == 3:
        return parents[0] / image_path.name
    elif len(parents) > 3:
        return image_path.relative_to(list(image_path.parents)[-3])
    else:
        raise ValueError(f"Invalid image path '{image_path}'")



@dataclass
class ExclusionZone:
    top_left: Tuple[float, float]
    bottom_right: Tuple[float, float]
    polygon: Polygon

    @staticmethod
    def parse(box_node: ET.Element) -> "ExclusionZone":
        left, top = float(box_node.attrib["xtl"]), float(box_node.attrib["ytl"])
        right, bottom = float(box_node.attrib["xbr"]), float(box_node.attrib["ybr"])
        polygon = Polygon([(left, top), (right, top), (right, bottom), (left, bottom)])
        return ExclusionZone(
            top_left=(top, left),
            bottom_right=(bottom, right),
            polygon=polygon
        )

    def height(self):
        return self.bottom_right[0] - self.top_left[0]

    def width(self):
        return self.bottom_right[1] - self.top_left[1]


class LineType(Enum):
    VISIBLE_CABLE = 0
    INFERRED_CABLE = 1
    NOT_CABLE = 2
    VISIBLE_OR_INFERRED = 3  # after merging cable continuations in annotations processing

    @staticmethod
    def parse(polyline_node: ET.Element) -> "LineType":
        label = polyline_node.attrib["label"]
        if label == "Cable visible":
            return LineType.VISIBLE_CABLE
        elif label == "Cable inferred":
            return LineType.INFERRED_CABLE
        else:
            return LineType.NOT_CABLE

    @staticmethod
    def from_selector(selector: str) -> "LineType":
        if selector == "visible":
            return LineType.VISIBLE_CABLE
        elif selector == "all":
            return LineType.VISIBLE_OR_INFERRED
        else:
            raise ValueError(f"Invalid selector '{selector}'")


@dataclass
class CableLine:
    points: List[List[float]]
    line: LineString
    type: LineType

    @staticmethod
    def parse(polyline_node: ET.Element, line_type: LineType) -> "CableLine":
        points_str = polyline_node.attrib["points"]
        points = [[float(ee) for ee in e.split(",")] for e in points_str.split(";")]
        line = shapely.geometry.LineString(points)
        return CableLine(points, line, line_type)

    def is_visible(self) -> bool:
        return self.type == LineType.VISIBLE_CABLE

    def is_inferred(self) -> bool:
        return self.type == LineType.INFERRED_CABLE

    def is_visible_or_inferred(self) -> bool:
        return self.type == LineType.VISIBLE_CABLE or self.type == LineType.INFERRED_CABLE or \
               self.type == LineType.VISIBLE_OR_INFERRED

    def length(self) -> float:
        points_npy = np.asarray(self.points)
        return np.sqrt(((points_npy[1:] - points_npy[:-1]) ** 2).sum(axis=1)).sum()


class PowerlinePoleType(Enum):
    TOWER = 0
    STICK = 1

    @staticmethod
    def parse(powerline_pole_node: ET.Element) -> "PowerlinePoleType":
        if powerline_pole_node.attrib["label"] == "Tower":
            return PowerlinePoleType.TOWER
        elif powerline_pole_node.attrib["label"] == "Stick":
            return PowerlinePoleType.STICK
        else:
            raise ValueError(f"Unexpected powerline pole label '{powerline_pole_node.attrib['label']}'")


@dataclass
class PowerlinePole:
    top_left: Tuple[float, float]
    bottom_right: Tuple[float, float]
    type: PowerlinePoleType

    @staticmethod
    def parse(powerline_pole_node: ET.Element) -> "PowerlinePole":
        top_left = float(powerline_pole_node.attrib["ytl"]), float(powerline_pole_node.attrib["xtl"])
        bottom_right = float(powerline_pole_node.attrib["ybr"]), float(powerline_pole_node.attrib["xbr"])
        powerline_pole_type = PowerlinePoleType.parse(powerline_pole_node)
        return PowerlinePole(top_left, bottom_right, powerline_pole_type)

    def is_tower(self):
        return self.type == PowerlinePoleType.TOWER

    def is_stick(self):
        return self.type == PowerlinePoleType.STICK

    def height(self):
        return self.bottom_right[0] - self.top_left[0]

    def width(self):
        return self.bottom_right[1] - self.top_left[1]

    def center_xy(self) -> List[float]:
        top, left = self.top_left
        bottom, right = self.bottom_right
        return [left + (right - left) / 2, top + (bottom - top) / 2]


@dataclass
class ImageAnnotations:
    relative_image_path: Path
    exclusion_zones: List[ExclusionZone]
    powerline_poles: List[PowerlinePole]
    cable_lines: List[CableLine]
    pose: Optional[CameraPose] = None

    @staticmethod
    def parse(image_node: ET.Element, poses_folder: Optional[Path] = None) -> "ImageAnnotations":
        relative_image_path = _fix_relative_image_path(image_node)
        exclusion_zones = [
            ExclusionZone.parse(box) for box in image_node.findall("box")
            if box.attrib["label"] == "Exclusion"
        ]

        powerline_poles = [
            PowerlinePole.parse(power_line_node) for power_line_node in image_node.findall("box")
            if power_line_node.attrib["label"] == "Tower" or power_line_node.attrib["label"] == "Stick"
        ]

        polylines_with_type = [(polyline, LineType.parse(polyline)) for polyline in image_node.findall("polyline")]
        cable_lines = [
            CableLine.parse(polyline, line_type) for (polyline, line_type) in polylines_with_type
            if line_type != LineType.NOT_CABLE
        ]

        if poses_folder is not None:
            timestamp = relative_image_path.stem
            pose_filepath = poses_folder / relative_image_path.parent / f"{timestamp}_pose.csv"
            pose = parse_pose(pose_filepath) if pose_filepath.exists() else None
        else:
            pose = None

        return ImageAnnotations(
            relative_image_path,
            exclusion_zones,
            powerline_poles,
            cable_lines,
            pose
        )

    def visible_cables(self) -> List[CableLine]:
        return list(filter(lambda cable: cable.is_visible(), self.cable_lines))

    def poles(self, max_height: Optional[float] = None):
        if max_height is None:
            return self.powerline_poles
        else:
            return list(filter(lambda pole: pole.height() <= max_height, self.powerline_poles))

    def cables(self, selector: str) -> List[CableLine]:
        if selector == "visible":
            return list(filter(lambda cable: cable.is_visible(), self.cable_lines))
        elif selector == "inferred":
            return list(filter(lambda cable: cable.is_inferred(), self.cable_lines))
        elif selector == "all":
            return list(filter(lambda cable: cable.is_visible_or_inferred(), self.cable_lines))
        else:
            raise ValueError(f"Unknown cable selector '{selector}'")

    def frame_timestamp(self) -> int:
        return int(self.relative_image_path.stem)

    def recording(self) -> str:
        return str(self.relative_image_path.parent)


def parse_annotations(annotations_folder: Path, poses_folder: Optional[Path] = None) -> List[ImageAnnotations]:
    if not annotations_folder.exists():
        raise FileNotFoundError(f"Annotations folder: {annotations_folder}")
    annotations_xml = _combine_xml_annotation_files(annotations_folder)
    return [ImageAnnotations.parse(image_node, poses_folder) for image_node in annotations_xml.findall("image")]