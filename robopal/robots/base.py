import abc
import logging
from typing import Union, List, Dict
import copy

import mujoco
import numpy as np
from robopal.commons import RobotGenerator


class BaseRobot:
    """ Base class for generating Data struct of the arm.

    :param name(str): robot name
    :param scene(str): scene name
    :param mount(str): mount name
    :param manipulator(str): manipulator name
    :param gripper(str): gripper name
    :param attached_body(str): Connect the end of manipulator and gripper at this body.
    :param xml_path(str): If you have specified the xml path of your local robot,
    it'll not automatically construct the xml file with input assets.
    """

    def __init__(self,
                 name: str = None,
                 scene: str = 'default',
                 mount: Union[str, List[str]] = None,
                 manipulator: Union[str, List[str]] = None,
                 gripper: Union[str, List[str]] = None,
                 attached_body: Union[str, List[str]] = None,
                 specified_xml: str = None
                 ):
        self.name = name

        if specified_xml is None:
            manipulator = [manipulator] if isinstance(manipulator, str) else manipulator

            self.mjcf_generator = RobotGenerator(
                scene=scene,
                mount=mount,
                manipulator=manipulator,
                gripper=gripper,
                attached_body=attached_body
            )
            self.add_assets()

            self.agent_num = len(manipulator)
            xml_path = self.mjcf_generator.save_and_load_xml()
        else:
            self.agent_num = 0  # by default, user should specify the agent number.
            assert self.agent_num > 0, 'Please specify the agent number by setting `self.agent_num`.'
            xml_path = specified_xml

        self.robot_model = mujoco.MjModel.from_xml_path(filename=xml_path, assets=None)
        self.robot_data = mujoco.MjData(self.robot_model)
        # deepcopy for computing kinematics.
        self.kine_data: mujoco.MjData = copy.deepcopy(self.robot_data)

        self.agents = [f'arm{i}' for i in range(self.agent_num)]
        logging.info(f'Activated agents: {self.agents}')
        
        # manipulator infos
        self._arm_joint_names = dict()
        self._arm_joint_indexes = dict()
        self._arm_actuator_names = dict()
        self._arm_actuator_indexes = dict()
        self.base_link_name = dict()
        self.end_name = dict()
        self.mani_joint_bounds = dict()  # Bounds at the joint limits

        # set end effector
        gripper = [gripper] if isinstance(gripper, str) else gripper
        from robopal.robots import END_MAP
        from robopal.robots.grippers import BaseEnd
        if specified_xml is None:
            self.end: Dict[str, BaseEnd] = {
                agent: END_MAP[gripper](self.robot_data) for agent, gripper in zip(self.agents, gripper)
            }
        else:
            self.end = None  # by default, user should specify the end effector.
            assert self.end is not None, 'Please specify the end effector by manual setting `self.end`.'

        # initial infos
        self.init_quat = dict()
        self.init_pos = dict()

    @property
    def arm_joint_names(self) -> Dict[str, np.ndarray]:
        """ robot info """
        return self._arm_joint_names
    
    @property
    def arm_joint_indexes(self) -> Dict[str, np.ndarray]:
        """ robot info """
        return self._arm_joint_indexes
    
    @arm_joint_names.setter
    def arm_joint_names(self, names: Dict[str, np.ndarray]):
        self._arm_joint_names = names
        for agent, names in names.items():
            index = [mujoco.mj_name2id(self.robot_model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in names]
            self._arm_joint_indexes[agent] = index
            
        self.mani_joint_bounds = {agent: (
            self.robot_model.jnt_range[self.arm_joint_indexes[agent], 0], 
            self.robot_model.jnt_range[self.arm_joint_indexes[agent], 1]
        ) for agent in self.agents}

    @property
    def arm_actuator_names(self) -> Dict[str, np.ndarray]:
        """ robot info """
        return self._arm_actuator_names
    
    @property
    def arm_actuator_indexes(self) -> Dict[str, np.ndarray]:
        """ robot info """
        return self._arm_actuator_indexes
    
    @arm_actuator_names.setter
    def arm_actuator_names(self, names: Dict[str, np.ndarray]):
        self._arm_actuator_names = names
        for agent, names in names.items():
            index = [mujoco.mj_name2id(self.robot_model, mujoco.mjtObj.mjOBJ_ACTUATOR, name) for name in names]
            self._arm_actuator_indexes[agent] = index

    @property
    def init_qpos(self) -> Dict[str, np.ndarray]:
        """ Robot's init joint position. """
        raise NotImplementedError

    @abc.abstractmethod
    def add_assets(self) -> None:
        """ Add objects into the xml file. """
        pass

    @property
    def jnt_num(self) -> Union[int, Dict[str, int]]:
        """ Number of joints. """
        return len(self.arm_joint_names[self.agents[0]])

    def get_arm_qpos(self, agent: str = 'arm0') -> np.ndarray:
        """ Get arm joint position of the specified agent.

        :param agent: agent name
        :return: joint position
        """
        return np.array([self.robot_data.joint(j).qpos[0] for j in self.arm_joint_names[agent]])

    def get_arm_qvel(self, agent: str = 'arm0') -> np.ndarray:
        """ Get arm joint velocity of the specified agent.

        :param agent: agent name
        :return: joint position
        """
        return np.array([self.robot_data.joint(j).qvel[0] for j in self.arm_joint_names[agent]])

    def get_arm_qacc(self, agent: str = 'arm0') -> np.ndarray:
        """ Get arm joint accelerate of the specified agent.

        :param agent: agent name
        :return: joint position
        """
        return np.array([self.robot_data.joint(j).qacc[0] for j in self.arm_joint_names[agent]])

    def get_mass_matrix(self, agent: str = 'arm0') -> np.ndarray:
        """ Get Mass Matrix
        ref https://github.com/ARISE-Initiative/robosuite/blob/master/robosuite/controllers/base_controller.py#L61

        :param agent: agent name
        :return: mass matrix
        """
        mass_matrix = np.ndarray(shape=(self.robot_model.nv, self.robot_model.nv), dtype=np.float64, order="C")
        # qM is inertia in joint space
        mujoco.mj_fullM(self.robot_model, mass_matrix, self.robot_data.qM)
        mass_matrix = np.reshape(mass_matrix, (len(self.robot_data.qvel), len(self.robot_data.qvel)))
        return mass_matrix[self.arm_joint_indexes[agent], :][:, self.arm_joint_indexes[agent]]

    def get_coriolis_gravity_compensation(self, agent: str = 'arm0') -> np.ndarray:
        return self.robot_data.qfrc_bias[self.arm_joint_indexes[agent]]
    
    def get_end_xpos(self, agent: str = 'arm0') -> np.ndarray:
        return self.robot_data.body(self.end_name[agent]).xpos.copy()

    def get_end_xquat(self, agent: str = 'arm0') -> np.ndarray:
        return self.robot_data.body(self.end_name[agent]).xquat.copy()

    def get_end_xmat(self, agent: str = 'arm0') -> np.ndarray:
        return self.robot_data.body(self.end_name[agent]).xmat.copy().reshape(3, 3)
    
    def get_end_xvel(self, agent: str = 'arm0') -> np.ndarray:
        """ Computing the end effector velocity

        :param agent: agent name
        :return: end effector velocity, 6*1, [v, w]
        """
        return np.dot(self.get_full_jac(agent), self.get_arm_qvel(agent))

    def get_base_xpos(self, agent: str = 'arm0') -> np.ndarray:
        return self.robot_data.body(self.base_link_name[agent]).xpos.copy()

    def get_base_xquat(self, agent: str = 'arm0') -> np.ndarray:
        return self.robot_data.body(self.base_link_name[agent]).xquat.copy()

    def get_base_xmat(self, agent: str = 'arm0') -> np.ndarray:
        return self.robot_data.body(self.base_link_name[agent]).xmat.copy().reshape(3, 3)
    
    def get_full_jac(self, agent: str = 'arm0') -> np.ndarray:
        """ Computes the full model Jacobian, expressed in the coordinate world frame.

        :param agent: agent name
        :return: Jacobian
        """
        bid = mujoco.mj_name2id(self.robot_model, mujoco.mjtObj.mjOBJ_BODY, self.end_name[agent])
        jacp = np.zeros((3, self.robot_model.nv))
        jacr = np.zeros((3, self.robot_model.nv))
        mujoco.mj_jacBody(self.robot_model, self.robot_data, jacp, jacr, bid)
        return np.concatenate([
            jacp[:, self.arm_joint_indexes[agent]], 
            jacr[:, self.arm_joint_indexes[agent]]
        ], axis=0).copy()
    
    def get_full_jac_pinv(self, agent: str = 'arm0') -> np.ndarray:
        """ Computes the full model Jacobian_pinv expressed in the coordinate world frame.

        :param agent: agent name
        :return: Jacobian_pinv
        """
        return np.linalg.pinv(self.get_full_jac(agent)).copy()
    
    def get_jac_dot(self, agent: str = 'arm0') -> np.ndarray:
        """ Computing the Jacobian_dot in the joint frame.
        https://github.com/google-deepmind/mujoco/issues/411#issuecomment-1211001685

        :param agent: agent name
        :return: Jacobian_dot
        """
        h = 1e-2
        J = self.get_full_jac(agent)

        original_qpos = self.robot_data.qpos.copy()
        mujoco.mj_integratePos(self.robot_model, self.robot_data.qpos, self.robot_data.qvel, h)
        mujoco.mj_comPos(self.robot_model, self.robot_data)
        mujoco.mj_kinematics(self.robot_model, self.robot_data)

        Jh = self.get_full_jac(agent)
        self.robot_data.qpos = original_qpos

        Jdot = (Jh - J) / h
        return Jdot
    