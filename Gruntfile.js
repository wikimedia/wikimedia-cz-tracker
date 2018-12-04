module.exports = function gruntConfig( grunt ) {
	grunt.initConfig( {
		pkg: grunt.file.readJSON( 'package.json' ),

		eslint: {
			options: {
				configFile: '.eslintrc.json'
			},
			src: [
				'Gruntfile.js',
				'static/**.js',
                '!static/**.min.js',
                '!static/jquery*.js',
			]
		},

		stylelint: {
			options: {
				configFile: '.stylelintrc.json'
			},
			src: [
				'static/**.css',
				'!static/**.min.css',
				'!static/jquery*.css',
			]
		}
	} );

	grunt.loadNpmTasks( 'grunt-eslint' );
	grunt.loadNpmTasks( 'grunt-stylelint' );

	grunt.registerTask( 'default', [ 'lint' ] );
	grunt.registerTask( 'lint', [ 'eslint', 'stylelint' ] );
};
