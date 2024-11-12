import csv
import pickle
from pathlib import Path
from typing import Optional, List

import numpy as np

from common.pose import CameraPose, GeoPosition, EulerRotation, translation

INTRINSICS_FILEPATH = Path(__file__).parent / "intrinsics.pkl"


def load_pickle(filepath: Path):
    with filepath.open("rb") as file:
        return pickle.load(file)


def build_intrinsic_matrix(f_x: float, f_y: float, x_0: float, y_0: float):
    """
    Creates intrinsic matrix from focal lengths and the optical center.
    Args:
        f_x: X focal length in pixels
        f_y: Y focal length in pixels
        x_0: X optical center coordinate in pixels (wrt top-left corner)
        y_0: Y optical center coordinate in pixels (wrt top-left corner)

    Returns:
        3x3 intrinsic matrix
    """
    return np.asarray([
        [f_x, 0, x_0],
        [0, f_y, y_0],
        [0, 0, 1]
    ])


def focal_length_mm(intrinsics_matrix: np.ndarray, sensor_width_mm: float, image_width_px: int) -> float:
    f_x = intrinsics_matrix[0, 0]
    f_y = intrinsics_matrix[1, 1]
    avg_f_px = (f_x + f_y) / 2
    # Focal in mm from px: https://answers.opencv.org/question/17076/conversion-focal-distance-from-mm-to-pixels/
    return  avg_f_px * sensor_width_mm / image_width_px


DEFAULT_INTRINSICS = build_intrinsic_matrix(2392.403520, 2394.356632, 2042.665689, 1485.345314)


def intrinsics(recording: Optional[str], warn: bool = False) -> np.ndarray:
    recording_to_intrinsics = load_pickle(INTRINSICS_FILEPATH)

    if recording is None:
        return DEFAULT_INTRINSICS.copy()

    if recording in recording_to_intrinsics:
        return recording_to_intrinsics[recording]
    else:
        if warn:
            print(f"WARNING: Intrinsics matrix not found for recording {recording}, resorting to the default one")
        return DEFAULT_INTRINSICS.copy()


poses_folder = Path("/home/bzdeco/Documents/EPFL/CVLab/Final/data_source/poses")


def parse_pose(pose_filepath: Path) -> CameraPose:
    with pose_filepath.open("r") as pose_file:
        reader = csv.reader(pose_file)
        coordinates_list = list(reader)[0]
        return CameraPose(
            position=GeoPosition(
                lat=float(coordinates_list[0]),
                lon=float(coordinates_list[1]),
                altitude=float(coordinates_list[2])
            ),
            rotation=EulerRotation.from_degrees(
                yaw=float(coordinates_list[3]),
                pitch=float(coordinates_list[4]),
                roll=float(coordinates_list[5])
            )
        )


DEFAULT_SPEED = 60  # km/h


def compute_camera_motion_velocities(recording: str, timestamps: List[int]) -> List[float]:
    if len(timestamps) == 1:
        return [DEFAULT_SPEED]  # default speed

    pose_filepaths = [poses_folder / recording / f"{timestamp}_pose.csv" for timestamp in sorted(timestamps)]
    poses = [
        parse_pose(pose_filepath) if pose_filepath.exists() else None
        for pose_filepath in pose_filepaths
    ]

    time_diff = np.diff(timestamps) * 1e-9  # in seconds
    displacements = np.asarray([
        np.linalg.norm(translation(start_pose, end_pose)) if start_pose is not None and end_pose is not None else 0
        for start_pose, end_pose in zip(poses[:-1], poses[1:])
    ])  # in meters
    velocities_m_per_s = displacements / time_diff
    velocities_km_per_h = velocities_m_per_s * 3.6

    velocities_km_per_h[velocities_km_per_h == 0] = DEFAULT_SPEED
    velocities_km_per_h[~np.isfinite(velocities_km_per_h)] = DEFAULT_SPEED

    return [velocities_km_per_h[0]] + velocities_km_per_h.tolist()  # extend by 1 element to provide for all poses
