"""Unit tests for the functions file."""

from __future__ import division, print_function, absolute_import

from numpy.testing import assert_equal, assert_allclose
import pytest
import unittest
import numpy as np
from scipy.optimize import check_grad

from safe_learning.functions import (Triangulation, ScipyDelaunay, GridWorld,
                                     PiecewiseConstant, DeterministicFunction,
                                     UncertainFunction, GPyGaussianProcess,
                                     QuadraticFunction, DimensionError,
                                     GPR_cached, GPflowGaussianProcess)

try:
    import GPy
except ImportError:
    GPy = None

try:
    import GPflow
    import tensorflow as tf
    from GPflow.param import AutoFlow
    from GPflow.tf_wraps import eye
except ImportError:
    GPflow = None
    tf = None


class DeterministicFuctionTest(unittest.TestCase):
    """Test the base class."""

    def test_errors(self):
        """Check notImplemented error."""
        f = DeterministicFunction()
        pytest.raises(NotImplementedError, f.evaluate, None)
        pytest.raises(NotImplementedError, f.gradient, None)

    def test_callable_constructor(self):
        """Test the from_callable constructor."""
        def test(a):
            return a

        c = DeterministicFunction.from_callable(test)
        assert_equal(c.evaluate(5), test(5))
        pytest.raises(NotImplementedError, c.gradient, 5)

        c = DeterministicFunction.from_callable(test, gradient=test)
        assert_equal(c.gradient(5), test(5))


class UncertainFunctionTest(unittest.TestCase):
    """Test the base class."""

    def test_errors(self):
        """Check notImplemented error."""
        f = UncertainFunction()
        pytest.raises(NotImplementedError, f.evaluate, None)
        pytest.raises(NotImplementedError, f.gradient, None)

    def test_mean_function(self):
        """Test the conversion to a deterministic function."""
        f = UncertainFunction()
        f.evaluate = lambda x: (1, 2)
        f.gradient = lambda x: (3, 4)
        fd = f.to_mean_function()
        assert(fd.evaluate(None) == 1)
        assert(fd.gradient(None) == 3)


@unittest.skipIf(GPy is None, 'GPy module not installed.')
class GPyTest(unittest.TestCase):
    """Test the GPY GP function class."""

    def setUp(self):
        """Create GP model."""
        x = np.array([[1, 0], [0, 1]])
        y = np.array([[0], [1]])
        kernel = GPy.kern.RBF(2)
        lik = GPy.likelihoods.Gaussian(variance=0.1**2)
        self.gp = GPy.core.GP(x, y, kernel, lik)
        self.beta = 2.
        self.ufun = GPyGaussianProcess(self.gp, beta=self.beta)
        self.beta_fun = lambda t: self.beta
        self.ufun2 = GPyGaussianProcess(self.gp, beta=self.beta_fun)
        self.test_points = np.array([[0.9, 0.1], [3., 2]])

    def test_evaluation(self):
        """Make sure evaluation works."""
        a1, b1 = self.ufun.evaluate(self.test_points)
        a2, b2 = self.gp.predict_noiseless(self.test_points)
        b2 = self.beta * np.sqrt(b2)
        assert_allclose(a1, a2)
        assert_allclose(b1, b2)

        # Test multiple inputs
        a1, b1 = self.ufun.evaluate(self.test_points[:, [0]],
                                    self.test_points[:, [1]])
        assert_allclose(a1, a2)
        assert_allclose(b1, b2)

    def test_gradient(self):
        """Make sure gradient works."""
        error_mean = check_grad(lambda x: self.ufun.evaluate(x)[0],
                                lambda x: self.ufun.gradient(x)[0],
                                self.test_points[0])

        error_std = check_grad(lambda x: self.ufun.evaluate(x)[1],
                               lambda x: self.ufun.gradient(x)[1],
                               self.test_points[0])

        assert_allclose(error_mean, 0, atol=1e-8)
        assert_allclose(error_std, 0, atol=1e-7)

    def test_new_data(self):
        """Test addting data points to the GP."""
        x = np.array([[1.2, 2.3]])
        y = np.array([[2.4]])
        self.ufun.add_data_point(x, y)

        gp = self.ufun.gaussian_process
        assert_allclose(gp.X, np.array([[1, 0],
                                        [0, 1],
                                        [1.2, 2.3]]))
        assert_allclose(gp.Y, np.array([[0], [1], [2.4]]))


@unittest.skipIf(tf is not None, 'GPflow is installed')
class NoTensorflowTest(unittest.TestCase):
    """Test in case tf is not installed."""

    def GPR_cached_test(self):
        """Check import error."""
        assert_raises(ImportError, GPR_cached, [], [], [])

    def GPflow_test(self):
        """Check import error."""
        assert_raises(ImportError, GPflowGaussianProcess, [])


@unittest.skipIf(tf is None, 'GPflow module not installed')
class GPR_cached_test(unittest.TestCase):
    """Test the GPR_cached class."""

    def setUp(self):
        """Create cached and uncached GPflow models and GPy model."""
        x = np.array([[1, 0], [0, 1]], dtype=float)
        y = np.array([[0], [1]], dtype=float)
        kernel = GPflow.kernels.RBF(2)
        self.gp = GPflow.gpr.GPR(x, y, kernel)
        self.gp_cached = GPR_cached(x, y, kernel)

        # Declare same gp in GPy to test predictive gradients
        kern_GPy = GPy.kern.RBF(input_dim=2, lengthscale=self.gp_cached.kern.lengthscales.value,
                                variance=self.gp_cached.kern.variance.value)
        lik = GPy.likelihoods.Gaussian(variance=self.gp_cached.likelihood.variance.value)
        self.gp_GPy = GPy.core.GP(x, y, kernel=kern_GPy, likelihood=lik)

        # Define test points
        self.test_points = np.array([[0.9, 0.1], [3., 2]])

    def test_predict_f(self):
        """Make sure predictions is same as in uncached case."""
        a1, b1 = self.gp_cached.predict_f(self.test_points)
        a2, b2 = self.gp.predict_f(self.test_points)
        assert_allclose(a1, a2)
        assert_allclose(b1, b2)

    def test_cholesky(self):
        """Test cholesky decomposition."""
        pass

    def test_predictive_gradients(self):
        """Test for derivative of mean and variance against GPy."""
        m_x, v_x = self.gp_cached.predictive_gradients(self.test_points)
        m_x_GPy, v_x_GPy = self.gp_GPy.predictive_gradients(self.test_points)

        assert_allclose(m_x - m_x_GPy, 0, atol=1e-7)
        assert_allclose(v_x - v_x_GPy, 0, atol=1e-7)


@unittest.skipIf(tf is None, 'GPflow module not installed')
class GPflowTest(unittest.TestCase):
    """Test the GPflowGaussianProcess function class."""

    def setUp(self):
        """Create GP model with GPflow and GPy."""
        x = np.array([[1, 0], [0, 1]], dtype=float)
        y = np.array([[0], [1]], dtype=float)
        kernel = GPflow.kernels.RBF(2)
        self.gp = GPR_cached(x, y, kernel)
        self.beta = 2
        self.ufun = GPflowGaussianProcess(self.gp, beta=self.beta)

        # Create same model in GPy
        kern_GPy = GPy.kern.RBF(input_dim=2, lengthscale=self.gp.kern.lengthscales.value,
                                variance=self.gp.kern.variance.value)
        lik = GPy.likelihoods.Gaussian(variance=self.gp.likelihood.variance.value)
        self.gp_GPy = GPy.core.GP(x, y, kernel=kern_GPy, likelihood=lik)
        self.ufun_GPy = GPyGaussianProcess(self.gp_GPy, beta=self.beta)

        self.beta_fun = lambda t: self.beta
        self.ufun2 = GPflowGaussianProcess(self.gp, beta=self.beta_fun)
        self.test_points = np.array([[0.9, 0.1], [3., 2]])

    def test_evaluation(self):
        """Make sure evaluation works."""
        a1, b1 = self.ufun.evaluate(self.test_points)
        a2, b2 = self.gp.predict_f(self.test_points)
        b2 = self.beta * np.sqrt(b2)
        assert_allclose(a1, a2)
        assert_allclose(b1, b2)

        # Test multiple inputs
        a1, b1 = self.ufun.evaluate(self.test_points[:, [0]],
                                    self.test_points[:, [1]])
        assert_allclose(a1, a2)
        assert_allclose(b1, b2)

    def test_evaluation_against_GPy(self):
        """Make sure evaluations is same as in GPy case."""
        a1, b1 = self.ufun.evaluate(self.test_points)
        a2, b2 = self.ufun_GPy.evaluate(self.test_points)
        assert_allclose(a1, a2)
        assert_allclose(b1, b2)

    def test_gradient_against_GPy(self):
        """Make sure gradient is same as in GPy case."""
        a1, b1 = self.ufun.gradient(self.test_points)
        a2, b2 = self.ufun_GPy.gradient(self.test_points)
        assert_allclose(a1 - a2, 0, atol=1e-7)
        assert_allclose(b1 - b2, 0, atol=1e-7)

    def test_gradient(self):
        """Make sure gradient works."""
        error_mean = check_grad(lambda x: self.ufun.evaluate(x)[0],
                                lambda x: self.ufun.gradient(x)[0],
                                self.test_points[0])
        error_std = check_grad(lambda x: self.ufun.evaluate(x)[1],
                               lambda x: self.ufun.gradient(x)[1],
                               self.test_points[1])
        assert_allclose(error_mean, 0, atol=1e-8)
        assert_allclose(error_std, 0, atol=1e-7)

    def test_new_data(self):
        """Test adding data points to the GP."""
        x = np.array([[1.2, 2.3]])
        y = np.array([[2.4]])

        self.ufun.add_data_point(x, y)

        assert_allclose(self.ufun.X, np.array([[1, 0],
                                              [0, 1],
                                              [1.2, 2.3]]))
        assert_allclose(self.ufun.Y, np.array([[0], [1], [2.4]]))

        # Check prediction is correct after adding data (cholesky update)
        self.ufun_GPy.add_data_point(x, y)

        a1, b1 = self.ufun.evaluate(self.test_points)
        a2, b2 = self.ufun_GPy.evaluate(self.test_points)
        assert_allclose(a1, a2)
        assert_allclose(b1, b2)


class QuadraticFunctionTest(unittest.TestCase):
    """Test the quadratic function."""

    def setUp(self):
        """Set up the test."""
        self.points = np.array([[0, 0],
                                [0, 1],
                                [1, 0],
                                [1, 1]])
        P = np.array([[1., 0.1],
                      [0.2, 2.]])
        self.quad = QuadraticFunction(P)

    def test_evaluate(self):
        """Test the evaluation of the quadratic function."""
        fval = self.quad.evaluate(self.points)
        true_fval = np.array([[0., 2., 1., 3.3]]).T
        assert_allclose(fval, true_fval)

    def test_gradient(self):
        """Test the gradient of the quadratic function."""
        fval = self.quad.gradient(self.points)
        true_fval = np.array([[0., 0.],
                              [0.4, 4.],
                              [2., .2],
                              [2.4, 4.2]])
        assert_allclose(fval, true_fval)


class ScipyDelaunayTest(unittest.TestCase):
    """Test the fake replacement for Scipy."""

    def test_init(self):
        """Test the initialization."""
        limits = [[-1, 1], [-1, 2]]
        num_points = [2, 6]
        sp_delaunay = ScipyDelaunay(limits, num_points)
        delaunay = Triangulation(limits, num_points)

        assert_equal(delaunay.nsimplex, sp_delaunay.nsimplex)
        assert_equal(delaunay.ndim, sp_delaunay.ndim)
        sp_delaunay.find_simplex(np.array([[0, 0]]))


class GridworldTest(unittest.TestCase):
    """Test the general GridWorld definitions."""

    def test_dimensions_error(self):
        """Test dimension errors."""
        limits = [[-1.1, 1.5], [2.2, 2.4]]
        num_points = [7, 8]
        grid = GridWorld(limits, num_points)

        pytest.raises(DimensionError, grid._check_dimensions,
                      np.array([[1, 2, 3]]))

        pytest.raises(DimensionError, grid._check_dimensions,
                      np.array([[1]]))

    def test_index_state_conversion(self):
        """Test all index conversions."""
        limits = [[-1.1, 1.5], [2.2, 2.4]]
        num_points = [7, 8]
        grid = GridWorld(limits, num_points)

        # Forward and backwards convert all indeces
        indeces = np.arange(grid.nindex)
        states = grid.index_to_state(indeces)
        indeces2 = grid.state_to_index(states)
        assert_equal(indeces, indeces2)

        # test 1D input
        grid.state_to_index([0, 2.3])
        grid.index_to_state(1)

        # Test rectangles
        rectangles = np.arange(grid.nrectangles)
        states = grid.rectangle_to_state(rectangles)
        rectangles2 = grid.state_to_rectangle(states + grid.unit_maxes / 2)
        assert_equal(rectangles, rectangles2)

        rectangle = grid.state_to_rectangle(100 * np.ones((1, 2)))
        assert_equal(rectangle, grid.nrectangles - 1)

        rectangle = grid.state_to_rectangle(-100 * np.ones((1, 2)))
        assert_equal(rectangle, 0)

        # Test rectangle corners
        corners = grid.rectangle_corner_index(rectangles)
        corner_states = grid.rectangle_to_state(rectangles)
        corners2 = grid.state_to_index(corner_states)
        assert_equal(corners, corners2)

        # Test point outside grid
        test_point = np.array([[-1.2, 2.]])
        index = grid.state_to_index(test_point)
        assert_equal(index, 0)

    def test_integer_numpoints(self):
        """Check integer numpoints argument."""
        grid = GridWorld([[1, 2], [3, 4]], 2)
        assert_equal(grid.num_points, np.array([2, 2]))

    def test_0d(self):
        """Check that initialization works for 1d-discretization."""
        grid = GridWorld([[0, 1]], 3)

        test = np.array([[0.1, 0.4, 0.9]]).T
        res = np.array([0, 1, 2])
        assert_allclose(grid.state_to_index(test), res)

        res = np.array([0, 0, 1])
        assert_allclose(grid.state_to_rectangle(test), res)
        assert_allclose(grid.rectangle_to_state(res), res[:, None] * 0.5)


class PiecewiseConstantTest(unittest.TestCase):
    """Test a piecewise constant function."""

    def test_init(self):
        """Test initialisation."""
        limits = [[-1, 1], [-1, 1]]
        npoints = 4
        pwc = PiecewiseConstant(limits, npoints, np.arange(16))
        assert_allclose(pwc.parameters, np.arange(16)[:, None])

    def test_evaluation(self):
        """Evaluation tests for piecewise constant function."""
        limits = [[-1, 1], [-1, 1]]
        npoints = 3
        pwc = PiecewiseConstant(limits, npoints)

        vertex_points = pwc.index_to_state(np.arange(pwc.nindex))
        vertex_values = np.sum(vertex_points, axis=1, keepdims=True)
        pwc.parameters = vertex_values

        test = pwc.evaluate(vertex_points)
        assert_allclose(test, vertex_values)

        outside_point = np.array([[-1.5, -1.5]])
        test1 = pwc.evaluate(outside_point)
        assert_allclose(test1, np.array([[-2]]))

        # Test constraint evaluation
        test2 = pwc.parameter_derivative(vertex_points)
        test2 = test2.toarray().dot(vertex_values)
        assert_allclose(test2, vertex_values)

    def test_gradient(self):
        """Test the gradient."""
        limits = [[-1, 1], [-1, 1]]
        npoints = 3
        pwc = PiecewiseConstant(limits, npoints)
        test_points = pwc.index_to_state(np.arange(pwc.nindex))
        gradient = pwc.gradient(test_points)
        assert_allclose(gradient, 0)


class DelaunayTest(unittest.TestCase):
    """Test the generalized Delaunay triangulation."""

    def test_find_simplex(self):
        """Test the simplices on the grid."""
        limits = [[-1, 1], [-1, 2]]
        num_points = [3, 7]
        delaunay = Triangulation(limits, num_points)

        # Test the basic properties
        assert_equal(delaunay.nrectangles, 2 * 6)
        assert_equal(delaunay.ndim, 2)
        assert_equal(delaunay.nsimplex, 2 * 2 * 6)
        assert_equal(delaunay.offset, np.array([-1, -1]))
        assert_equal(delaunay.unit_maxes,
                     np.array([2, 3]) / (np.array(num_points) - 1))
        assert_equal(delaunay.nrectangles, 2 * 6)

        # test the simplex indices
        lower = delaunay.triangulation.find_simplex(np.array([0, 0])).squeeze()
        upper = 1 - lower

        test_points = np.array([[0, 0],
                                [0.9, 0.45],
                                [1.1, 0],
                                [1.9, 2.9]])

        test_points += np.array(limits)[:, 0]

        true_result = np.array([lower, upper, 6 * 2 + lower, 11 * 2 + upper])
        result = delaunay.find_simplex(test_points)

        assert_allclose(result, true_result)

        # Test the ability to find simplices
        simplices = delaunay.simplices(result)
        true_simplices = np.array([[0, 1, 7],
                                   [1, 7, 8],
                                   [7, 8, 14],
                                   [13, 19, 20]])
        assert_equal(np.sort(simplices, axis=1), true_simplices)

        # Test point ouside domain (should map to bottom left and top right)
        assert_equal(lower, delaunay.find_simplex(np.array([[-100., -100.]])))
        assert_equal(delaunay.nsimplex - 1 - lower,
                     delaunay.find_simplex(np.array([[100., 100.]])))

    def test_values(self):
        """Test the evaluation function."""
        eps = 1e-10

        delaunay = Triangulation([[0, 1], [0, 1]], [2, 2])

        test_points = np.array([[0, 0],
                                [1 - eps, 0],
                                [0, 1 - eps],
                                [0.5 - eps, 0.5 - eps],
                                [0, 0.5],
                                [0.5, 0]])
        nodes = delaunay.state_to_index(np.array([[0, 0],
                                                  [1, 0],
                                                  [0, 1]]))

        H = delaunay.parameter_derivative(test_points).toarray()

        true_H = np.zeros((len(test_points), delaunay.nindex),
                          dtype=np.float)
        true_H[0, nodes[0]] = 1
        true_H[1, nodes[1]] = 1
        true_H[2, nodes[2]] = 1
        true_H[3, nodes[[1, 2]]] = 0.5
        true_H[4, nodes[[0, 2]]] = 0.5
        true_H[5, nodes[[0, 1]]] = 0.5

        assert_allclose(H, true_H, atol=1e-7)

        # Test value property
        values = np.random.rand(delaunay.nindex)
        delaunay.parameters = values
        v1 = H.dot(values)[:, None]
        v2 = delaunay.evaluate(test_points)
        assert_allclose(v1, v2)

        # Test the projections
        test_point = np.array([[-0.5, -0.5]])
        delaunay.parameters = np.array([0, 1, 1, 1])
        unprojected = delaunay.evaluate(test_point)
        delaunay.project = True
        projected = delaunay.evaluate(test_point)

        assert_allclose(projected, np.array([[0]]))
        assert_allclose(unprojected, np.array([[-1]]))

    def test_multiple_dimensions(self):
        """Test delaunay in three dimensions."""
        limits = [[0, 1]] * 3
        delaunay = Triangulation(limits, [2] * 3)
        assert_equal(delaunay.ndim, 3)
        assert_equal(delaunay.nrectangles, 1)
        assert_equal(delaunay.nsimplex, np.math.factorial(3))

        corner_points = np.array([[0, 0, 0],
                                  [1, 0, 0],
                                  [0, 1, 0],
                                  [0, 0, 1],
                                  [0, 1, 1],
                                  [1, 1, 0],
                                  [1, 0, 1],
                                  [1, 1, 1]], dtype=np.float)

        values = np.sum(delaunay.index_to_state(np.arange(8)), axis=1) / 3

        test_points = np.vstack((corner_points,
                                 np.array([[0, 0, 0.5],
                                           [0.5, 0, 0],
                                           [0, 0.5, 0],
                                           [0.5, 0.5, 0.5]])))
        corner_values = np.sum(corner_points, axis=1) / 3
        true_values = np.hstack((corner_values,
                                 np.array([1 / 6, 1 / 6, 1 / 6, 1 / 2])))

        delaunay.parameters = values
        result = delaunay.evaluate(test_points)
        assert_allclose(result, true_values[:, None], atol=1e-5)

    def test_gradient(self):
        """Test the gradient_at function."""
        delaunay = Triangulation([[0, 1], [0, 1]], [2, 2])

        points = np.array([[0, 0],
                           [1, 0],
                           [0, 1],
                           [1, 1]], dtype=np.int)
        nodes = delaunay.state_to_index(points)

        # Simplex with node values:
        # 3 - 1
        # | \ |
        # 1 - 2
        # --> x

        values = np.zeros(delaunay.nindex)
        values[nodes] = [1, 2, 3, 1]

        test_points = np.array([[0.01, 0.01],
                                [0.99, 0.99]])

        true_grad = np.array([[1, 2], [-2, -1]])

        # Construct true H (gradient as function of values)
        true_H = np.zeros((2 * delaunay.ndim, delaunay.nindex))

        true_H[0, nodes[[0, 1]]] = [-1, 1]
        true_H[1, nodes[[0, 2]]] = [-1, 1]
        true_H[2, nodes[[2, 3]]] = [-1, 1]
        true_H[3, nodes[[1, 3]]] = [-1, 1]

        # Evaluate gradient with and without values
        H = delaunay.gradient_parameter_derivative(test_points).toarray()
        delaunay.parameters = values
        grad = delaunay.gradient(test_points)

        # Compare
        assert_allclose(grad, true_grad)
        assert_allclose(H, true_H)
        assert_allclose(true_grad, H.dot(values).reshape(-1, delaunay.ndim))

    def test_1d(self):
        """Test the triangulation for 1D inputs."""
        delaunay = Triangulation([[0, 1]], 3, vertex_values=[0, 0.5, 0])
        vertex_values = delaunay.parameters

        test_points = np.array([[0, 0.2, 0.5, 0.6, 0.9, 1.]]).T
        test_point = test_points[[0], :]

        simplices = delaunay.find_simplex(test_points)
        true_simplices = np.array([0, 0, 1, 1, 1, 1])
        assert_allclose(simplices, true_simplices)
        assert_allclose(delaunay.find_simplex(test_point),
                        true_simplices[[0]])

        values = delaunay.evaluate(test_points)
        true_values = np.array([0, 0.2, 0.5, 0.4, 0.1, 0])[:, None]
        assert_allclose(values, true_values)

        value_constraint = delaunay.parameter_derivative(test_points)
        values = value_constraint.toarray().dot(vertex_values)
        assert_allclose(values, true_values)

        gradient = delaunay.gradient(test_points)
        true_gradient = np.array([1, 1, -1, -1, -1, -1])[:, None]
        assert_allclose(gradient, true_gradient)

        gradient_deriv = delaunay.gradient_parameter_derivative(test_points)
        gradient = gradient_deriv.toarray().dot(vertex_values)
        assert_allclose(gradient.reshape(-1, 1), true_gradient)


if __name__ == '__main__':
    unittest.main()
