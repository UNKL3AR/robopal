import numpy as np
import logging

from robopal.envs.task_ik_ctrl_env import PosCtrlEnv
from robopal.robots.diana_med import DianaPainting

logging.basicConfig(level=logging.INFO)


class DrawerEnv(PosCtrlEnv):
    """
    The control frequency of the robot is of f = 20 Hz. This is achieved by applying the same action
    in 50 subsequent simulator step (with a time step of dt = 0.0005 s) before returning the control to the robot.
    """
    metadata = {"render_modes": ["human", "rgb_array"]}

    def __init__(self,
                 robot=DianaPainting(),
                 is_render=True,
                 renderer="viewer",
                 render_mode='human',
                 control_freq=40,
                 enable_camera_viewer=False,
                 cam_mode='rgb',
                 controller='JNTIMP',
                 is_interpolate=False,
                 is_pd=False,
                 ):
        super().__init__(
            robot=robot,
            is_render=is_render,
            renderer=renderer,
            control_freq=control_freq,
            enable_camera_viewer=enable_camera_viewer,
            cam_mode=cam_mode,
            controller=controller,
            is_interpolate=is_interpolate,
            is_pd=is_pd,
        )
        self.name = 'Painting-v1'

        self.obs_dim = (17,)
        self.goal_dim = (3,)
        self.action_dim = (4,)

        self.max_action = 1.0
        self.min_action = -1.0

        self.max_episode_steps = 100
        self._timestep = 0

        self.goal_pos = None

        assert render_mode is None or render_mode in self.metadata["render_modes"]
        self.render_mode = render_mode

    def step(self, action) -> tuple:
        """ Take one step in the environment.

        :param action:  The action space is 4-dimensional, with the first 3 dimensions corresponding to the desired
        position of the block in Cartesian coordinates, and the last dimension corresponding to the
        desired gripper opening (0 for closed, 1 for open).
        :return: obs, reward, terminated, truncated, info
        """
        self._timestep += 1

        pos_offset = 0.01 * action[:3]
        actual_pos_action = self.kdl_solver.fk(self.robot.arm_qpos)[0] + pos_offset

        pos_max_bound = np.array([0.65, 0.2, 0.4])
        pos_min_bound = np.array([0.3, -0.2, 0.14])
        actual_pos_action = actual_pos_action.clip(pos_min_bound, pos_max_bound)

        super().step(actual_pos_action[:3])

        obs = self._get_obs()

        reward = self.compute_rewards()
        terminated = False
        truncated = False
        if self._timestep >= self.max_episode_steps:
            truncated = True
        info = self._get_info()

        if self.render_mode == 'human':
            self.render()
            self.renderer.render_traj(self.get_site_pos('0_gripper_frame'))

        return obs, reward, terminated, truncated, info

    def inner_step(self, action):
        super().inner_step(action)

    def compute_rewards(self, info: dict = None):
        """ Sparse Reward: the returned reward can have two values: -1 if the block hasn’t reached its final
        target position, and 0 if the block is in the final target position (the block is considered to have
        reached the goal if the Euclidean distance between both is lower than 0.05 m).
        """
        return 0.0

    def _get_obs(self) -> np.ndarray:
        """ The observation space is 16-dimensional, with the first 3 dimensions corresponding to the position
        of the block, the next 3 dimensions corresponding to the position of the goal, the next 3 dimensions
        corresponding to the position of the gripper, the next 3 dimensions corresponding to the vector
        between the block and the gripper, and the last dimension corresponding to the current gripper opening.
        """
        obs = np.zeros(self.obs_dim)

        return obs.copy()

    def _get_info(self) -> dict:
        return {}

    def reset(self, seed=None):
        super().reset()
        self._timestep = 0

        obs = self._get_obs()
        info = self._get_info()

        if self.render_mode == 'human':
            self.render()
            self.renderer.traj.clear()

        return obs, info


if __name__ == "__main__":

    env = DrawerEnv()
    env.reset()

    for t in range(int(1e6)):
        action = np.random.uniform(env.min_action, env.max_action, env.action_dim)
        s_, r, terminated, truncated, _ = env.step(action)
        if truncated:
            env.reset()
