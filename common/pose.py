import math
from dataclasses import dataclass
from typing import Union

import numpy as np
import pyproj
import quaternion
from pyproj import CRS

MERCATOR_EPSG = 3857
WGS84_EPSG = 4326
GEODETIC_EPSG = 4978
mercator_crs = CRS.from_epsg(MERCATOR_EPSG)
latlon_crs = CRS.from_epsg(WGS84_EPSG)
geocentric_cartesian_crs = CRS.from_epsg(GEODETIC_EPSG)


def wgs84_to_mercator_crs_transformer() -> pyproj.transformer.Transformer:
    return pyproj.transformer.Transformer.from_crs(latlon_crs, mercator_crs)


def wgs84_to_geodetic_crs_transformer() -> pyproj.transformer.Transformer:
    return pyproj.transformer.Transformer.from_crs(latlon_crs, geocentric_cartesian_crs)


def geodetic_to_wgs84_crs_transformer() -> pyproj.transformer.Transformer:
    return pyproj.transformer.Transformer.from_crs(geocentric_cartesian_crs, latlon_crs)


wgs84_to_geodetic = wgs84_to_geodetic_crs_transformer()
wgs84_to_mercator = wgs84_to_mercator_crs_transformer()
geodetic_to_wgs84 = geodetic_to_wgs84_crs_transformer()


@dataclass(eq=True, frozen=True)  # hashable
class GeoPosition:
    lat: float  # degrees
    lon: float  # degrees
    altitude: float

    def to_geodetic_xyz(self) -> np.ndarray:
        x, y, z = wgs84_to_geodetic.transform(self.lat, self.lon, self.altitude)
        return np.array([x, y, z])

    @staticmethod
    def from_xyz(x: float, y: float, z: float) -> "GeoPosition":
        lat, lon, altitude = geodetic_to_wgs84.transform(x, y, z)
        return GeoPosition(lat, lon, altitude)


@dataclass(eq=True, frozen=True)  # hashable
class EulerRotation:  # in radians
    yaw: float
    pitch: float
    roll: float

    @staticmethod
    def from_degrees(yaw: float, pitch: float, roll: float) -> "EulerRotation":
        return EulerRotation(math.radians(yaw), math.radians(pitch), math.radians(roll))

    @staticmethod
    def from_direction_xyz(direction: np.ndarray) -> "EulerRotation":
        # Cannot tell roll from the direction vector, it needs to be set manually
        unit_direction = direction / np.linalg.norm(direction)
        xz_normal = np.asarray([0, 1, 0])

        xz_projection = unit_direction - np.dot(unit_direction, xz_normal) * xz_normal
        xz_projection_norm = np.maximum(np.linalg.norm(xz_projection), 1e-8)
        unit_xz_projection = xz_projection / xz_projection_norm

        yaw_angle = np.arctan2(unit_xz_projection[0], unit_xz_projection[2])
        # Projection norm always > 0, pitch is negative when plane is heading down -> negate direction Y coord
        pitch_angle = np.arctan2(- unit_direction[1], xz_projection_norm)

        return EulerRotation(yaw=yaw_angle, pitch=pitch_angle, roll=0)

    def in_degrees(self) -> "EulerRotation":
        return EulerRotation(math.degrees(self.yaw), math.degrees(self.pitch), math.degrees(self.roll))

    def as_quaternion_xyz(self) -> np.quaternion:
        yaw_quat = quaternion.from_rotation_vector(self.yaw * np.array([0, 1, 0]))
        yaw = quaternion.as_rotation_matrix(yaw_quat)
        pitch_quat = quaternion.from_rotation_vector(self.pitch * yaw @ np.array([1, 0, 0]))
        pitch = quaternion.as_rotation_matrix(pitch_quat)
        roll_quat = quaternion.from_rotation_vector(self.roll * pitch @ yaw @ np.array([0, 0, 1]))
        return roll_quat * pitch_quat * yaw_quat

    def as_quaternion_frd(self) -> np.quaternion:
        cos_roll = np.cos(self.roll / 2)
        sin_roll = np.sin(self.roll / 2)
        cos_pitch = np.cos(self.pitch / 2)
        sin_pitch = np.sin(self.pitch / 2)
        cos_yaw = np.cos(self.yaw / 2)
        sin_yaw = np.sin(self.yaw / 2)

        w = cos_roll * cos_pitch * cos_yaw + sin_roll * sin_pitch * sin_yaw
        x = sin_roll * cos_pitch * cos_yaw - cos_roll * sin_pitch * sin_yaw
        y = cos_roll * sin_pitch * cos_yaw + sin_roll * cos_pitch * sin_yaw
        z = cos_roll * cos_pitch * sin_yaw - sin_roll * sin_pitch * cos_yaw

        return np.quaternion(w, x, y, z)


@dataclass(eq=True, frozen=True)  # hashable
class CameraPose:
    position: GeoPosition
    rotation: EulerRotation

    def is_complete(self) -> bool:
        return all(map(lambda value: value is not None and not np.isnan(value), [self.position.lat, self.position.lon]))


def rotation(
    ref_pose: CameraPose, current_pose: CameraPose, coord_system: str = "xyz", as_matrix: bool = False
) -> Union[np.quaternion, np.ndarray]:
    if coord_system == "xyz":
        current_quaternion = current_pose.rotation.as_quaternion_xyz()
        ref_quaternion = ref_pose.rotation.as_quaternion_xyz()
    elif coord_system == "frd":
        current_quaternion = current_pose.rotation.as_quaternion_frd()
        ref_quaternion = ref_pose.rotation.as_quaternion_frd()
    else:
        raise ValueError(f"Invalid coordinate system: {coord_system}")

    rot_quaternion = current_quaternion / ref_quaternion  # simplified, assuming two poses are in the same local tangent plane
    if as_matrix:
        return quaternion.as_rotation_matrix(rot_quaternion)
    else:
        return rot_quaternion


def earth_to_ned_local_tangent_plane_rotation(origin_position: GeoPosition) -> np.ndarray:
    phi, lam = math.radians(origin_position.lat), math.radians(origin_position.lon)
    return np.array([
        [-np.sin(phi) * np.cos(lam), -np.sin(phi) * np.sin(lam), np.cos(phi)],
        [-np.sin(lam), np.cos(lam), 0],
        [-np.cos(phi) * np.cos(lam), -np.cos(phi) * np.sin(lam), -np.sin(phi)]
    ])


def frd_translation_to_xyz(frd_translation_vector: np.ndarray) -> np.ndarray:
    forward, right, down = frd_translation_vector
    return np.asarray([right, down, forward])


def translation(ref_pose: CameraPose, current_pose: CameraPose) -> np.ndarray:
    ref_geo_xyz = ref_pose.position.to_geodetic_xyz()
    current_geo_xyz = current_pose.position.to_geodetic_xyz()
    xyz_translation = current_geo_xyz - ref_geo_xyz

    # Convert current pose to local tangent plane with origin at reference pose and axis aligned with plane orientation (FRD)
    rot_ltp = earth_to_ned_local_tangent_plane_rotation(ref_pose.position)
    translation_ned_ltp = rot_ltp @ xyz_translation
    rot_0 = quaternion.as_rotation_matrix(1 / ref_pose.rotation.as_quaternion_frd())
    translation_frd_ltp = rot_0 @ translation_ned_ltp

    return frd_translation_to_xyz(translation_frd_ltp)
