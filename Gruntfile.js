module.exports = function gruntConfig( grunt ) {
	grunt.initConfig( {
		pkg: grunt.file.readJSON( 'package.json' ),

		eslint: {
			options: {
				configFile: '.eslintrc.json'
			},
			src: [
				'Gruntfile.js',
				'static/**/*.js',
				'!static/**/*.min.js',
				'!static/**/jquery*.js'
			]
		},

		stylelint: {
			options: {
				configFile: '.stylelintrc.json'
			},
			src: [
				'static/**/*.css',
				'!static/**/*.min.css',
				'!static/**/jquery*.css'
			]
		},

		htmllint: {
			options: {
				htmllintrc: '.htmllintrc.json'
			},
			src: [
				'trackersite/**/*.html'
			]
		},

		i18nlint: {
			options: {
				attributes: [],
				templateDelimiters: [
					[ '{{', '}}' ],
					[ '{% blocktrans', '{% endblocktrans %}' ],
					[ '{%', '%}' ],
					[ '{#', '#}' ],
					[ '<!-- i18n-lint disable -->', '<!-- i18n-lint enable -->' ]
				]
			},
			src: [
				'trackersite/**/*.html'
			]
		}
	} );

	grunt.loadNpmTasks( 'grunt-eslint' );
	grunt.loadNpmTasks( 'grunt-stylelint' );
	grunt.loadNpmTasks( 'grunt-htmllint' );
	grunt.loadNpmTasks( 'grunt-i18nlint' );
	grunt.registerTask( 'default', [ 'lint' ] );
	grunt.registerTask( 'lint', [ 'eslint', 'i18nlint' ] ); // Stylelint emergency disabled, T213247 --Urbanecm
};
